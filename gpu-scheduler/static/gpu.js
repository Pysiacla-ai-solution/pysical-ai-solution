document.addEventListener('DOMContentLoaded', () => {
  const jobForm = document.getElementById('jobForm');
  const refreshBtn = document.getElementById('refreshBtn');
  
  // 초기 로딩
  fetchGpuMetrics();
  fetchJobQueue();

  // 2초마다 자동 새로고침 (실시간 모니터링)
  setInterval(() => {
      fetchGpuMetrics();
      fetchJobQueue();
  }, 10000);

  // 새로고침 버튼 클릭 이벤트
  if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
          fetchGpuMetrics();
          fetchJobQueue();
      });
  }

  // 작업 제출 (Submit) 처리
  if (jobForm) {
      jobForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          
          const fileInput = document.getElementById('fileInput');
          const userId = document.getElementById('userId').value;
          const vramGb = document.getElementById('vramInput').value;
          const partition = document.getElementById('partitionSelect').value;
          const qos = document.getElementById('qosSelect').value;
          const resultDiv = document.getElementById('submitResult');
  
          if (!fileInput.files[0]) {
              alert("스크립트 파일을 선택해주세요.");
              return;
          }
  
          const formData = new FormData();
          formData.append('file', fileInput.files[0]);
          // GB -> Bytes 변환
          const vramBytes = vramGb * 1024 * 1024 * 1024;
  
          // 쿼리 파라미터 구성
          const url = `/api/v1/jobs/submit?user_id=${userId}&vram_required=${vramBytes}&partition=${partition}&qos=${qos}`;
  
          try {
              resultDiv.innerHTML = '<span style="color: #aaa;">제출 중...</span>';
              const res = await fetch(url, {
                  method: 'POST',
                  body: formData
              });
  
              if (res.ok) {
                  const data = await res.json();
                  resultDiv.innerHTML = `<span style="color: #69db7c;">✅ 제출 성공! (ID: ${data.id.substring(0,8)})</span>`;
                  jobForm.reset();
                  fetchJobQueue(); // 즉시 갱신
              } else {
                  const err = await res.json();
                  resultDiv.innerHTML = `<span style="color: #fa5252;">❌ 실패: ${err.detail || '알 수 없는 오류'}</span>`;
              }
          } catch (error) {
              console.error(error);
              resultDiv.innerHTML = `<span style="color: #fa5252;">❌ 서버 통신 오류</span>`;
          }
      });
  }
});

// 1. GPU 상태 조회
async function fetchGpuMetrics() {
  const area = document.getElementById('gpuMetricsArea');
  if (!area) return; // HTML에 영역이 없으면 패스

  try {
      const res = await fetch('/api/v1/gpu/metrics');
      if (!res.ok) return;
      const data = await res.json();

      area.innerHTML = '';
      data.forEach(gpu => {
          const usedGb = (gpu.memory_used / (1024**3)).toFixed(1);
          const totalGb = (gpu.memory_total / (1024**3)).toFixed(1);
          const memPercent = Math.round((gpu.memory_used / gpu.memory_total) * 100);
          
          // 다크 모드에 어울리는 카드 디자인
          const html = `
              <div class="metric-card" style="background:#25262b; border:1px solid #373a40; border-radius:8px; padding:15px; margin-bottom:10px; color:#fff; display:flex; justify-content:space-between; align-items:center;">
                  <div>
                      <strong style="color:#74c0fc;">${gpu.name}</strong> <br>
                      <small style="color:#868e96;">GPU ID: ${gpu.gpu_id}</small>
                  </div>
                  <div style="text-align: right;">
                      <div style="font-size:0.9rem; margin-bottom:5px;">MEM: ${usedGb} / ${totalGb} GB (${memPercent}%)</div>
                      <div style="background: #373a40; width: 120px; height: 8px; border-radius: 4px; overflow: hidden;">
                          <div style="background: #228be6; width: ${memPercent}%; height: 100%;"></div>
                      </div>
                  </div>
              </div>
          `;
          area.insertAdjacentHTML('beforeend', html);
      });
  } catch (e) {
      console.error("GPU Fetch Error:", e);
  }
}

// 2. 작업 대기열 조회
async function fetchJobQueue() {
  const tbody = document.getElementById('jobsTableBody');
  if (!tbody) return;

  try {
      const res = await fetch('/api/v1/jobs/queue');
      if (!res.ok) return;
      const jobs = await res.json();

      tbody.innerHTML = '';
      
      if (jobs.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding: 20px; color: #868e96;">대기 중인 작업이 없습니다.</td></tr>';
          return;
      }

      jobs.forEach(job => {
          const vramGb = (job.vram_required / (1024**3)).toFixed(1);
          
          // 상태별 뱃지 색상
          let badgeColor = '#fab005'; // QUEUED (노랑)
          let badgeBg = '#fab00520';
          
          if (job.status === 'RUNNING') { badgeColor = '#40c057'; badgeBg = '#40c05720'; }
          if (job.status === 'FAILED') { badgeColor = '#fa5252'; badgeBg = '#fa525220'; }
          if (job.status === 'COMPLETED') { badgeColor = '#ced4da'; badgeBg = '#ced4da20'; }

          const row = `
              <tr style="border-bottom: 1px solid #373a40;">
                  <td style="padding: 12px;">
                      <span style="color:${badgeColor}; background:${badgeBg}; padding:4px 8px; border-radius:4px; font-weight:bold; font-size:0.8rem;">
                          ${job.status}
                      </span>
                  </td>
                  <td style="color:#fff; font-weight:bold;">${Math.round(job.priority_score).toLocaleString()}</td>
                  <td style="color:#e9ecef;">${job.user_id}</td>
                  <td style="color:#adb5bd;">${job.partition} / ${job.qos}</td>
                  <td style="color:#adb5bd;">${vramGb} GB</td>
                  <td style="font-family:monospace; color:#495057;">${job.id.substring(0,8)}</td>
              </tr>
          `;
          tbody.insertAdjacentHTML('beforeend', row);
      });
  } catch (e) {
      console.error("Queue Fetch Error:", e);
  }
}