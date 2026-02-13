package gpuscheduler;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.mindrot.jbcrypt.BCrypt;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.sql.*;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;

/**
 * PostgreSQL + 세션 + JWT 기반 로그인 인증 서버 (교육용).
 *
 * - DB 스키마: db_schema_postgres.sql 의 users 테이블 사용
 * - 포트: 8080 (FastAPI GPU 스케줄러는 8000 사용)
 */
public class SimpleAuthServer {

    // ==== DB CONFIG (PostgreSQL) ==== //
    private static final String DB_URL = "jdbc:postgresql://localhost:5432/gpu_scheduler";
    private static final String DB_USER = "gpu_user";
    private static final String DB_PASSWORD = "gpu_password";

    // ==== SESSION STORE ==== //
    private static final Map<String, User> SESSION_STORE = new ConcurrentHashMap<>();
    private static final String SESSION_COOKIE_NAME = "SESSION_ID";

    // ==== JWT COOKIE 이름 ==== //
    private static final String JWT_COOKIE_NAME = "ACCESS_TOKEN";

    // ==== (선택) 프론트에서 로그인 여부 판단용 쿠키 ==== //
    private static final String APP_AUTH_COOKIE_NAME = "APP_AUTH";

    // 프론트엔드 (예: FastAPI가 제공하는 gpu.html) origin
    private static final String DEV_FRONTEND_ORIGIN = "http://localhost:8000";

    private static final boolean DEBUG = true;

    public static void main(String[] args) throws Exception {
        // PostgreSQL JDBC 드라이버
        Class.forName("org.postgresql.Driver");

        System.out.println("=== SimpleAuthServer (PostgreSQL) ===");
        System.out.println("Server started at http://localhost:8080");

        UserRepository userRepository = new JdbcUserRepository(DB_URL, DB_USER, DB_PASSWORD);
        AuthService authService = new AuthService(userRepository);

        HttpServer server = HttpServer.create(new InetSocketAddress(8080), 0);
        server.setExecutor(Executors.newFixedThreadPool(10));

        // GET / -> login.html 제공 (리소스는 classpath:gpuscheduler/web/login.html 기준)
        server.createContext("/", exchange -> {
            if ("GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                serveResource(exchange, "gpuscheduler/web/login.html", "text/html; charset=utf-8");
            } else {
                methodNotAllowed(exchange);
            }
        });

        // POST /api/signup
        server.createContext("/api/signup", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }
            try {
                Map<String, String> params = parseFormBody(exchange);
                String username = trimToNull(params.get("username"));
                String password = params.get("password");
                if (password != null) password = password.trim();

                if (isBlank(username) || isBlank(password)) {
                    writeJson(exchange, 400, "{\"ok\":false,\"error\":\"username and password are required\"}");
                    return;
                }

                authService.signUp(username, password);
                writeJson(exchange, 200, "{\"ok\":true}");
            } catch (SQLIntegrityConstraintViolationException dup) {
                writeJson(exchange, 400, "{\"ok\":false,\"error\":\"username already exists\"}");
            } catch (Exception e) {
                e.printStackTrace();
                writeJson(exchange, 500, "{\"ok\":false,\"error\":\"signup error\"}");
            }
        });

        // POST /api/login
        server.createContext("/api/login", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }

            try {
                Map<String, String> params = parseFormBody(exchange);
                String username = params.get("username");
                String password = params.get("password");

                if (DEBUG) {
                    System.out.println("[LOGIN] username=" + username + ", pwLen=" + (password == null ? -1 : password.length()));
                }

                if (isBlank(username) || isBlank(password)) {
                    writeJson(exchange, 400, "{\"ok\":false,\"error\":\"username and password are required\"}");
                    return;
                }

                User user = authService.login(username, password);
                if (user == null) {
                    writeJson(exchange, 401, "{\"ok\":false,\"error\":\"invalid credentials\"}");
                    return;
                }

                String sessionId = UUID.randomUUID().toString();
                SESSION_STORE.put(sessionId, user);
                exchange.getResponseHeaders().add("Set-Cookie",
                        cookie(SESSION_COOKIE_NAME, sessionId, true, -1));

                String jwt = JwtUtil.createToken(user);
                exchange.getResponseHeaders().add("Set-Cookie",
                        cookie(JWT_COOKIE_NAME, jwt, true, -1));

                exchange.getResponseHeaders().add("Set-Cookie",
                        cookie(APP_AUTH_COOKIE_NAME, "1", false, -1));

                writeJson(exchange, 200, "{\"ok\":true}");
            } catch (Exception e) {
                e.printStackTrace();
                writeJson(exchange, 500, "{\"ok\":false,\"error\":\"login error\"}");
            }
        });

        // GET /api/auth/check
        server.createContext("/api/auth/check", exchange -> {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                addCorsHeaders(exchange);
                exchange.sendResponseHeaders(204, -1);
                exchange.close();
                return;
            }
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }
            addCorsHeaders(exchange);

            String sessionId = getCookieValue(exchange, SESSION_COOKIE_NAME);
            User sessionUser = null;
            if (!isBlank(sessionId)) {
                sessionUser = SESSION_STORE.get(sessionId);
            }

            String token = getCookieValue(exchange, JWT_COOKIE_NAME);
            boolean jwtOk = false;
            String jwtUsername = null;
            if (!isBlank(token)) {
                try {
                    DecodedJWT decoded = JwtUtil.verifyToken(token);
                    jwtOk = true;
                    jwtUsername = decoded.getClaim("username").asString();
                } catch (JWTVerificationException ex) {
                    jwtOk = false;
                } catch (Exception ex) {
                    jwtOk = false;
                }
            }

            if (sessionUser == null && !jwtOk) {
                writeJson(exchange, 401, "{\"ok\":false,\"reason\":\"UNAUTHORIZED\"}");
                return;
            }

            String username = sessionUser != null ? sessionUser.getUsername() : jwtUsername;
            String body = "{\"ok\":true,\"username\":\"" + escapeJson(username) + "\"}";
            writeJson(exchange, 200, body);
        });

        server.start();
    }

    // ==== CORS ====
    private static void addCorsHeaders(HttpExchange exchange) {
        exchange.getResponseHeaders().set("Access-Control-Allow-Origin", DEV_FRONTEND_ORIGIN);
        exchange.getResponseHeaders().set("Access-Control-Allow-Credentials", "true");
        exchange.getResponseHeaders().set("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
        exchange.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type");
        exchange.getResponseHeaders().set("Vary", "Origin");
    }

    // ==== 리소스/응답 헬퍼 ====

    private static void serveResource(HttpExchange exchange, String resourcePath, String contentType) throws IOException {
        InputStream is = SimpleAuthServer.class.getClassLoader().getResourceAsStream(resourcePath);
        if (is == null) {
            notFound(exchange);
            return;
        }
        byte[] bytes = is.readAllBytes();
        exchange.getResponseHeaders().add("Content-Type", contentType);
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void writeJson(HttpExchange exchange, int status, String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void methodNotAllowed(HttpExchange exchange) throws IOException {
        byte[] bytes = "Method Not Allowed".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(405, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void notFound(HttpExchange exchange) throws IOException {
        byte[] bytes = "Not Found".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(404, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static Map<String, String> parseFormBody(HttpExchange exchange) throws IOException {
        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        Map<String, String> params = new HashMap<>();
        for (String pair : body.split("&")) {
            if (pair.isEmpty()) continue;
            String[] kv = pair.split("=", 2);
            String key = urlDecode(kv[0]);
            String value = kv.length > 1 ? urlDecode(kv[1]) : "";
            params.put(key, value);
        }
        return params;
    }

    private static String urlDecode(String s) {
        return URLDecoder.decode(s, StandardCharsets.UTF_8);
    }

    private static boolean isBlank(String s) {
        return s == null || s.trim().isEmpty();
    }

    private static String trimToNull(String s) {
        if (s == null) return null;
        String t = s.trim();
        return t.isEmpty() ? null : t;
    }

    private static String getCookieValue(HttpExchange exchange, String name) {
        List<String> cookies = exchange.getRequestHeaders().get("Cookie");
        if (cookies == null) return null;
        for (String header : cookies) {
            String[] parts = header.split(";\\s*");
            for (String part : parts) {
                String[] kv = part.split("=", 2);
                if (kv.length == 2 && name.equals(kv[0])) {
                    return kv[1];
                }
            }
        }
        return null;
    }

    private static String cookie(String name, String value, boolean httpOnly, int maxAgeSeconds) {
        StringBuilder sb = new StringBuilder();
        sb.append(name).append("=").append(value == null ? "" : value);
        sb.append("; Path=/");
        if (maxAgeSeconds >= 0) sb.append("; Max-Age=").append(maxAgeSeconds);
        if (httpOnly) sb.append("; HttpOnly");
        sb.append("; SameSite=Lax");
        return sb.toString();
    }

    private static String escapeJson(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    // ==== 도메인 / 레포지토리 / 서비스 ====

    public static class User {
        private Long id;
        private String username;
        private String password;

        public Long getId() { return id; }
        public void setId(Long id) { this.id = id; }
        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }
        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }
    }

    public interface UserRepository {
        void save(User user) throws Exception;
        User findByUsername(String username) throws Exception;
    }

    public static class JdbcUserRepository implements UserRepository {
        private final String url;
        private final String user;
        private final String password;

        public JdbcUserRepository(String url, String user, String password) {
            this.url = url;
            this.user = user;
            this.password = password;
        }

        private Connection getConnection() throws SQLException {
            return DriverManager.getConnection(url, user, password);
        }

        @Override
        public void save(User u) throws Exception {
            String sql = "INSERT INTO users(username, password) VALUES(?, ?)";
            try (Connection conn = getConnection();
                 PreparedStatement ps = conn.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
                ps.setString(1, u.getUsername());
                ps.setString(2, u.getPassword());
                ps.executeUpdate();
                try (ResultSet rs = ps.getGeneratedKeys()) {
                    if (rs.next()) {
                        u.setId(rs.getLong(1));
                    }
                }
            }
        }

        @Override
        public User findByUsername(String username) throws Exception {
            String sql = "SELECT id, username, password FROM users WHERE username = ?";
            try (Connection conn = getConnection();
                 PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setString(1, username);
                try (ResultSet rs = ps.executeQuery()) {
                    if (rs.next()) {
                        User u = new User();
                        u.setId(rs.getLong("id"));
                        u.setUsername(rs.getString("username"));
                        u.setPassword(rs.getString("password"));
                        return u;
                    }
                }
            }
            return null;
        }
    }

    public static class AuthService {
        private final UserRepository userRepository;

        public AuthService(UserRepository userRepository) {
            this.userRepository = userRepository;
        }

        public void signUp(String username, String rawPassword) throws Exception {
            username = trimToNull(username);
            if (rawPassword != null) rawPassword = rawPassword.trim();

            User existing = userRepository.findByUsername(username);
            if (existing != null) {
                throw new SQLIntegrityConstraintViolationException("username already exists");
            }

            String hashed = BCrypt.hashpw(rawPassword, BCrypt.gensalt(12));

            User u = new User();
            u.setUsername(username);
            u.setPassword(hashed);
            userRepository.save(u);
        }

        public User login(String username, String rawPassword) throws Exception {
            username = trimToNull(username);
            if (rawPassword != null) rawPassword = rawPassword.trim();

            User u = userRepository.findByUsername(username);
            if (u == null) {
                if (DEBUG) System.out.println("[AUTH] user not found: " + username);
                return null;
            }

            boolean ok = BCrypt.checkpw(rawPassword, u.getPassword());
            if (!ok) return null;
            return u;
        }
    }

    // ==== JWT 유틸 ====
    public static class JwtUtil {
        private static final String SECRET = "RANDOM_SECRET_KEY";
        private static final Algorithm ALG = Algorithm.HMAC256(SECRET);
        private static final String ISSUER = "gpu-auth-server";

        public static String createToken(User user) {
            Instant now = Instant.now();
            return JWT.create()
                    .withIssuer(ISSUER)
                    .withIssuedAt(java.util.Date.from(now))
                    .withExpiresAt(java.util.Date.from(now.plus(1, ChronoUnit.HOURS)))
                    .withSubject(String.valueOf(user.getId()))
                    .withClaim("username", user.getUsername())
                    .sign(ALG);
    }

    public static DecodedJWT verifyToken(String token) throws JWTVerificationException {
        JWTVerifier verifier = JWT.require(ALG)
                .withIssuer(ISSUER)
                .build();
        return verifier.verify(token);
    }
}
}

