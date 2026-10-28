// Task 4: Timeline tiến triển của bệnh nhân (biểu đồ + bảng các lần chụp).
// Dùng Chart.js (index.html đã nạp sẵn).

let timelineChart = null;

async function showTimeline(caseId) {
  if (!caseId) return;
  try {
    const response = await fetch(`/api/cases/${caseId}/timeline`, {
      credentials: "same-origin",
    });
    if (!response.ok) return;
    renderTimeline(await response.json());
  } catch (err) {
    console.error("Không tải được timeline", err);
  }
}

window.showTimeline = showTimeline;

function renderTimeline(data) {
  const resultsContainer = document.getElementById("resultsState");
  if (!resultsContainer) return;

  // Tạo khung timeline ở cuối khu vực kết quả
  let box = document.getElementById("timelineBox");
  if (!box) {
    box = document.createElement("div");
    box.id = "timelineBox";
    box.style.cssText =
      "margin-top:28px;padding:22px;border:1.5px solid #94a3b8;border-radius:18px;background:#ffffff;box-shadow:0 10px 30px rgba(15,23,42,0.08);scroll-margin-top:20px;";
    resultsContainer.append(box);
  }
  box.innerHTML = "";
  if (timelineChart) {
    timelineChart.destroy();
    timelineChart = null;
  }

  // Header card Timeline
  const header = document.createElement("div");
  header.style.cssText =
    "display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;border-bottom:1px solid #e2e8f0;padding-bottom:12px;flex-wrap:wrap;gap:8px;";
  header.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;">
            <span style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:10px;background:#eff6ff;color:#2563eb;flex-shrink:0;">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
      </span>
      <div>
        <h4 style="margin:0;font-size:18px;font-weight:700;color:#0f172a;">Tiến triển theo thời gian (Timeline)</h4>
        <small style="color:#64748b;">Lịch sử sàng lọc và biến đổi tổn thương qua các lần khám</small>
      </div>
    </div>
    <span style="background:#e0f2fe;color:#0369a1;padding:6px 14px;border-radius:999px;font-size:12.5px;font-weight:600;">
      Theo dõi dài hạn
    </span>
  `;
  box.append(header);

  const points = data.points || [];
  if (points.length < 2) {
    const note = document.createElement("div");
    note.style.cssText =
      "padding:16px;background:#f8fafc;border:1px dashed #cbd5e1;border-radius:12px;color:#475569;font-size:13.5px;text-align:center;";
    note.innerHTML = `
      <p style="margin:0 0 6px 0;font-weight:600;color:#334155;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:text-bottom;margin-right:4px;" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg> Bệnh nhân này hiện có ${points.length} lần phân tích được lưu.</p>
      <span style="color:#64748b;">Hệ thống cần từ <strong>2 lần phân tích trở lên</strong> của cùng một bệnh nhân để vẽ biểu đồ và đánh giá xu hướng tiến triển.</span>
    `;
    box.append(note);
    return;
  }

  // Nút nhảy nhanh từ đầu kết quả xuống Timeline (ngay dưới verdictCard)
  let jumpBtn = document.getElementById("timelineJumpBtn");
  if (!jumpBtn) {
    jumpBtn = document.createElement("button");
    jumpBtn.id = "timelineJumpBtn";
    jumpBtn.type = "button";
    jumpBtn.style.cssText =
      "display:flex;align-items:center;justify-content:center;gap:10px;width:100%;font-size:14px;font-weight:700;padding:12px 18px;margin:16px 0;background:#ecfdf5;color:#047857;border:1.5px solid #6ee7b7;border-radius:12px;cursor:pointer;box-shadow:0 4px 14px rgba(16,185,129,0.15);transition:all .2s;";
    jumpBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:middle;margin-right:4px;" aria-hidden="true"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg> <span>Có ${points.length} lần khám trước! Bấm để xem Biểu đồ tiến triển bên dưới ↓</span>`;
    jumpBtn.onmouseover = () => { jumpBtn.style.background = "#d1fae5"; jumpBtn.style.transform = "translateY(-1px)"; };
    jumpBtn.onmouseout = () => { jumpBtn.style.background = "#ecfdf5"; jumpBtn.style.transform = "none"; };
    jumpBtn.onclick = () => {
      box.scrollIntoView({ behavior: "smooth", block: "start" });
      box.style.outline = "3px solid #10b981";
      setTimeout(() => { box.style.outline = "none"; }, 1500);
    };
    const verdictCard = document.getElementById("verdictCard");
    if (verdictCard && verdictCard.parentNode) {
      verdictCard.parentNode.insertBefore(jumpBtn, verdictCard.nextSibling);
    }
  } else {
    jumpBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:middle;margin-right:4px;" aria-hidden="true"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg> <span>Có ${points.length} lần khám trước! Bấm để xem Biểu đồ tiến triển bên dưới ↓</span>`;
  }

  // Kết nối nút ở thanh công cụ sau phân tích (nếu có)
  const viewTimelineBtn = document.getElementById("viewTimelineBtn");
  if (viewTimelineBtn) {
    viewTimelineBtn.onclick = () => {
      box.scrollIntoView({ behavior: "smooth", block: "start" });
      box.style.outline = "3px solid #10b981";
      setTimeout(() => { box.style.outline = "none"; }, 1500);
    };
  }

  // Nhận xét xu hướng
  if (data.trend) {
    const trendBox = document.createElement("div");
    const isWorse = data.trend.change > 0;
    const bg = isWorse ? "#fef2f2" : "#f0fdf4";
    const color = isWorse ? "#b91c1c" : "#15803d";
    const border = isWorse ? "#fecaca" : "#bbf7d0";
    const sign = isWorse ? "+" : "";

    trendBox.style.cssText = `margin-bottom:16px;padding:12px 16px;border-radius:10px;background:${bg};border:1px solid ${border};color:${color};font-size:14px;`;
    trendBox.innerHTML = `
      <strong>Đánh giá xu hướng:</strong> ${data.trend.label} 
      (${sign}${data.trend.change}% xác suất ác tính so với lần khám đầu tiên).
    `;
    box.append(trendBox);
  }

  // Biểu đồ xác suất ác tính theo thời gian
  const chartWrap = document.createElement("div");
  chartWrap.style.cssText = "height:240px;margin-bottom:18px;";
  const canvas = document.createElement("canvas");
  chartWrap.append(canvas);
  box.append(chartWrap);

  const fmt = (iso) => new Date(iso).toLocaleDateString("vi-VN");
  timelineChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: points.map((p) => fmt(p.date)),
      datasets: [
        {
          label: "Xác suất ác tính (%)",
          data: points.map((p) => p.prob_malignant),
          tension: 0.25,
          borderColor: "#dc2626",
          backgroundColor: "rgba(220, 38, 38, 0.1)",
          fill: true,
          pointRadius: 5,
          pointHoverRadius: 7,
          pointBackgroundColor: "#dc2626",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top" },
      },
      scales: {
        y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } },
      },
    },
  });

  // Bảng các lần chụp
  const tableWrap = document.createElement("div");
  tableWrap.style.cssText = "overflow-x:auto;";
  const table = document.createElement("table");
  table.style.cssText = "width:100%;border-collapse:collapse;font-size:13.5px;color:#334155;";
  
  const head = table.insertRow();
  ["Ngày khám", "Mã ca", "Chẩn đoán AI", "Xác suất ác tính", "Độ tin cậy"].forEach((text) => {
    const th = document.createElement("th");
    th.textContent = text;
    th.style.cssText =
      "text-align:left;padding:8px 10px;background:#f8fafc;border-bottom:2px solid #e2e8f0;font-weight:600;";
    head.append(th);
  });

  points.forEach((p, idx) => {
    const row = table.insertRow();
    row.style.borderBottom = "1px solid #f1f5f9";
    if (idx % 2 === 1) row.style.background = "#fafafa";

    const tdDate = row.insertCell();
    tdDate.textContent = fmt(p.date);
    tdDate.style.padding = "8px 10px";

    const tdCode = row.insertCell();
    tdCode.textContent = p.case_code || "—";
    tdCode.style.padding = "8px 10px";

    const tdClass = row.insertCell();
    tdClass.innerHTML = `<strong>${p.predicted_class}</strong>`;
    tdClass.style.padding = "8px 10px";

    const tdMalignant = row.insertCell();
    tdMalignant.textContent = `${p.prob_malignant}%`;
    tdMalignant.style.padding = "8px 10px";
    if (p.prob_malignant >= 50) tdMalignant.style.color = "#dc2626";

    const tdConf = row.insertCell();
    tdConf.textContent = `${p.confidence}%`;
    tdConf.style.padding = "8px 10px";
  });

  tableWrap.append(table);
  box.append(tableWrap);
}
