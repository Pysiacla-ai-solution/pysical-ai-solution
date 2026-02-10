function $(sel){ return document.querySelector(sel); }

const state = {
  // ✅ data-mode 없고 data-page만 있는 페이지도 정상 인식
  mode: document.body.dataset.mode || document.body.dataset.page || "dashboard",
  sending: false,
};

function setActiveNav(){
  const path = location.pathname;
  document.querySelectorAll(".nav a").forEach(a=>{
    const href = a.getAttribute("href");
    if(href && path.endsWith(href)) a.classList.add("active");
  });
}

function escapeHtml(s){
  return (s ?? "").replace(/[&<>"']/g, (m)=>({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[m]));
}

function appendMessage(role, text, metaHtml=""){
  const box = $(".messages");
  if(!box) return;

  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = `
    <div>${escapeHtml(text).replace(/\n/g,"<br>")}</div>
    ${metaHtml ? `<div class="meta">${metaHtml}</div>` : ""}
  `;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
}

function buildPayload(){
  const query = ($("#query")?.value || "").trim();
  const robot = {
    type: ($("#robotType")?.value || "").trim(),
    dof:  ($("#robotDof")?.value || "").trim(),
    mass: ($("#robotMass")?.value || "").trim(),
    notes:($("#robotNotes")?.value || "").trim(),
  };
  return { mode: state.mode, query, robot };
}

// ✅ 백엔드 연결
async function callAssistantAPI(payload){
  const res = await fetch("/api/assistant/query", {
    method:"POST",
    headers:{ "Content-Type":"application/json" },
    credentials:"include",
    body: JSON.stringify(payload),
  });
  if(!res.ok){
    const t = await res.text();
    throw new Error(`API ${res.status}: ${t}`);
  }
  return await res.json();
}

// ✅ API 실패 시 데모 응답
function mockAnswer(payload){
  if(payload.mode === "spec"){
    return {
      answer:
`(데모) Humanoid Locomotion 예시

[필수]
- term: action_rate
  mapping: mdp.action_rate_12
  why: 관절 급변 억제(안정)

- term: track_lin_vel_xy_exp
  mapping: mdp.track_lin_vel_xy_exp
  why: 목표 속도 추종(수렴)

[선택]
- term: undesired_contacts
  mapping: mdp.undesired_contacts
  why: 미끄러짐/접촉 제어

추천 Observation: joint pos/vel · base vel · orientation`,
      sources: ["Isaac Lab 예제 config", "관련 논문 Reward Engineering 섹션"]
    };
  }

  if(payload.mode === "params"){
    return {
      answer:
`(데모) 시작 파라미터 범위 예시

- Kp (stiffness): 20 ~ 50
- torque limit: ~ 200 Nm
- action scaling: 0.5 (처음엔 낮게)`,
      sources: ["유사 로봇 실험 setup(논문)", "Isaac Lab task 설정 예시"]
    };
  }

  if(payload.mode === "template"){
    return {
      answer:
`(데모) 환경 템플릿 예시

- action space: joint position control
- domain randomization:
  - friction: 0.2 ~ 1.0
  - mass: ±10%
  - push: 10초마다 랜덤`,
      sources: ["오픈소스 config", "Isaac Lab task YAML"]
    };
  }

  return { answer: "(데모) 질문을 입력해줘.", sources: [] };
}

async function onSend(){
  if(state.sending) return;
  const payload = buildPayload();

  if(!payload.query){
    appendMessage("assistant", "질문(Task)을 먼저 입력해줘.");
    return;
  }

  state.sending = true;
  $("#sendBtn") && ($("#sendBtn").disabled = true);

  // 1. 화면에 사용자 메시지 추가
  appendMessage("user", payload.query);

  // 2. 입력창 비우기 및 포커스 (추가된 부분)
  if($("#query")) {
    $("#query").value = "";
    $("#query").focus(); 
  }

  try{
    const data = await callAssistantAPI(payload);
    const src = (data.sources || []).map(s=>`<li>${escapeHtml(s)}</li>`).join("");
    const meta = src ? `<div class="sources"><b>출처</b><ul>${src}</ul></div>` : "";
    appendMessage("assistant", data.answer || "(빈 응답)", meta);
  }catch(e){
    const data = mockAnswer(payload);
    const src = (data.sources || []).map(s=>`<li>${escapeHtml(s)}</li>`).join("");
    const meta = src ? `<div class="sources"><b>(데모) 참고</b><ul>${src}</ul></div>` : "";
    appendMessage("assistant", data.answer, meta);
  }finally{
    state.sending = false;
    $("#sendBtn") && ($("#sendBtn").disabled = false);
  }
}

function onClearChat(){
  const box = $(".messages");
  if(box) box.innerHTML = "";
  appendMessage("assistant", "대화가 초기화되었습니다. 새 질문을 입력하세요.");
  if($("#query")) {
    $("#query").value = "";
    $("#query").focus();
  }
}

/* ===== 프로필 저장/초기화 (localStorage) ===== */
const PROFILE_KEY = "isaac_robot_profile_v1";

function getEl(id) { return document.getElementById(id); }

function readProfileFromForm() {
  return {
    robotType: getEl("robotType")?.value?.trim() ?? "",
    robotDof:  getEl("robotDof")?.value?.trim() ?? "",
    robotMass: getEl("robotMass")?.value?.trim() ?? "",
    robotNotes:getEl("robotNotes")?.value?.trim() ?? "",
    savedAt: new Date().toISOString()
  };
}

function applyProfileToForm(profile) {
  if (!profile) return;
  if (getEl("robotType")) getEl("robotType").value = profile.robotType ?? "";
  if (getEl("robotDof"))  getEl("robotDof").value  = profile.robotDof ?? "";
  if (getEl("robotMass")) getEl("robotMass").value = profile.robotMass ?? "";
  if (getEl("robotNotes"))getEl("robotNotes").value= profile.robotNotes ?? "";
}

function saveProfile() {
  const profile = readProfileFromForm();
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  alert("프로필이 저장되었습니다.");
}

function loadProfile() {
  const raw = localStorage.getItem(PROFILE_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function clearProfile() {
  localStorage.removeItem(PROFILE_KEY);

  if (getEl("robotType")) getEl("robotType").value = "";
  if (getEl("robotDof"))  getEl("robotDof").value = "";
  if (getEl("robotMass")) getEl("robotMass").value = "";
  if (getEl("robotNotes"))getEl("robotNotes").value = "";

  alert("프로필이 초기화되었습니다.");
}

function bind(){
  setActiveNav();

  $("#sendBtn")?.addEventListener("click", onSend);
  $("#clearChatBtn")?.addEventListener("click", onClearChat);

  $("#query")?.addEventListener("keydown", (e)=>{
    if(e.key === "Enter" && !e.shiftKey){
      e.preventDefault();
      onSend();
    }
  });

  // 프로필: 자동 로드 + 버튼 연결
  const profile = loadProfile();
  applyProfileToForm(profile);

  $("#saveProfileBtn")?.addEventListener("click", saveProfile);
  $("#clearProfileBtn")?.addEventListener("click", clearProfile);

  // ✅ 첫 안내 메시지 설정
  const introMap = {
    spec: "Task를 적으면 Reward/Observation 설정 이름을 정리해줍니다. (term · mapping · 1줄 이유)",
    params: "로봇 스펙 기준으로 시작 파라미터 범위를 정리해줍니다. (Kp · torque · scaling)",
    template: "새 로봇/환경을 위한 기본 설정 템플릿을 생성합니다.",
    home: "",
    dashboard: "",
  };

  const box = $(".messages");
  if(box && box.children.length === 0){
    const msg = introMap[state.mode] ?? "";
    if(msg) appendMessage("assistant", msg);
  }
}

document.addEventListener("DOMContentLoaded", bind);