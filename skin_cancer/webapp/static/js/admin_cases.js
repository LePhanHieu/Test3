(() => {
  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char],
    );
  const display = (value) =>
    value === null || value === undefined || value === ""
      ? "—"
      : escapeHtml(value);
  const fmtDate = (date) =>
    date ? new Date(date).toLocaleDateString("vi-VN") : "—";
  const statusLabels = {
    CREATED: "Mới tạo",
    UPLOADED: "Đã tải ảnh",
    ANALYZED: "Đã phân tích",
    REVIEWED: "Đã đánh giá",
    COMPLETED: "Hoàn thành",
  };
  const classLabels = {
    MEL: "U hắc tố (Melanoma)",
    NV: "Nốt ruồi sắc tố (Nevus)",
    BCC: "Ung thư biểu mô tế bào đáy",
    SCC: "Ung thư biểu mô tế bào vảy",
    AK: "Dày sừng ánh sáng",
    AKIEC: "Dày sừng ánh sáng",
    BKL: "Dày sừng lành tính",
    DF: "U xơ da",
    VASC: "Tổn thương mạch máu",
  };
  const icon = (name) =>
    ({
      person:
        '<circle cx="12" cy="7" r="3"/><path d="M5.5 21v-2a6.5 6.5 0 0 1 13 0v2"/>',
      scan: '<circle cx="12" cy="12" r="3"/><path d="M5 3h3M3 5v3M19 3h-3M21 5v3M3 16v3h3M21 16v3h-3"/>',
      note: '<path d="M7 3h8l4 4v14H7z"/><path d="M15 3v5h4M10 13h6M10 17h5"/>',
      care: '<rect x="4" y="7" width="16" height="14" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M4 12h16M12 10v5M9.5 12.5h5"/>',
      image:
        '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1"/><path d="m4 18 6-6 4 3 3-4 4 5"/>',
    })[name];
  const sectionTitle = (name, title) =>
    `<div class="case-section-heading"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icon(name)}</svg><strong>${title}</strong></div>`;
  const section = (name, title, content) =>
    `<section class="case-medical-section">${sectionTitle(name, title)}${content}</section>`;
  const safePercent = (value) =>
    typeof value === "number" && Number.isFinite(value)
      ? `${(value * 100).toFixed(1)}%`
      : "—";
  let page = 1;
  let pages = 1;
  let requestId = 0;
  let searchTimer;

  async function getJson(url) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(
        data.message || data.description || "Không thể tải dữ liệu ca khám.",
      );
    return data;
  }

  async function loadAdminCases() {
    const id = ++requestId;
    const params = new URLSearchParams({ page: String(page) });
    [
      ["search", "#case-search"],
      ["status", "#case-status"],
      ["doctor", "#case-doctor"],
      ["start", "#case-from"],
      ["end", "#case-to"],
    ].forEach(([name, field]) => {
      if ($(field).value.trim()) params.set(name, $(field).value.trim());
    });
    $("#case-count").textContent = "Đang tải danh sách...";
    try {
      const data = await getJson(`/api/admin/cases?${params}`);
      if (id !== requestId) return;
      $("#case-total").textContent = Number(data.metrics.total).toLocaleString(
        "vi-VN",
      );
      $("#case-processing").textContent = Number(
        data.metrics.processing,
      ).toLocaleString("vi-VN");
      $("#case-completed").textContent = Number(
        data.metrics.completed,
      ).toLocaleString("vi-VN");
      const doctorSelect = $("#case-doctor");
      const selected = doctorSelect.value;
      doctorSelect.replaceChildren(
        new Option("Tất cả bác sĩ", ""),
        ...(data.doctors || []).map(
          (doctor) => new Option(doctor.name, doctor.id),
        ),
      );
      doctorSelect.value = selected;
      page = data.page;
      pages = data.pages;
      $("#case-count").textContent = `Tìm thấy ${data.total} ca khám`;
      $("#case-page").textContent = `Trang ${page}/${pages}`;
      $("#case-prev").disabled = page <= 1;
      $("#case-next").disabled = page >= pages;
      $("#admin-cases-table").innerHTML = data.cases.length
        ? data.cases
            .map(
              (item) =>
                `<tr><td><b>${display(item.code)}</b></td><td>${display(item.patient)}</td><td>${display(item.doctor)}</td><td>${fmtDate(item.created_at)}</td><td><span class="status-chip ${item.status === "COMPLETED" ? "success" : "warning"}">${display(statusLabels[item.status] || item.status)}</span></td><td><button type="button" class="text-btn" data-view-case="${item.id}">Xem chi tiết</button></td></tr>`,
            )
            .join("")
        : '<tr><td colspan="6" class="loading">Không có ca khám phù hợp. Hãy thử xóa bộ lọc.</td></tr>';
    } catch (error) {
      if (id !== requestId) return;
      $("#case-count").textContent = "Không tải được dữ liệu.";
      $("#admin-cases-table").innerHTML =
        `<tr><td colspan="6" class="loading">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  async function openCaseDetail(caseId) {
    const modal = $("#admin-case-modal");
    modal.classList.add("open");
    $("#case-detail-title").textContent = "Chi tiết chẩn đoán & Hướng điều trị";
    $("#case-detail-subtitle").textContent = "Đang tải thông tin ca khám...";
    $("#admin-case-detail").textContent = "Đang tải chi tiết...";
    try {
      const item = await getJson(`/api/admin/cases/${caseId}`);
      if (!modal.classList.contains("open")) return;
      $("#case-detail-subtitle").innerHTML =
        `Mã hồ sơ: <b>${display(item.code)}</b> · Ngày khám: ${fmtDate(item.created_at)}`;
      const overview = section(
        "person",
        "Thông tin ca khám & Bác sĩ phụ trách",
        `<div class="case-medical-facts"><span>Vị trí tổn thương: <b>${display(item.lesion_location)}</b></span><span>Bác sĩ chẩn đoán: <b>${display(item.doctor)}</b></span><span>Trạng thái ca: <b>${display(item.status)}</b></span><span>Bệnh nhân: <b>${display(item.patient)}</b></span></div>`,
      );
      const analyses = (item.analyses || []).flatMap((analysis) =>
        (analysis.results || []).map((result) => ({ analysis, result })),
      );
      const classifications = analyses
        .map(
          ({ analysis, result }) =>
            `<div class="case-medical-result"><span class="case-ai-pill">Phân loại AI: ${result.binary === 0 ? "Lành tính" : result.binary === 1 ? "Nghi ngờ ác tính" : "Chưa xác định"} · Độ tin cậy: ${safePercent(result.probability)}</span><p><b>${display(classLabels[result.class] || result.class)}</b></p><p class="case-medical-muted">Mô hình: ${display(result.model)} · Phân tích #${analysis.id}</p>${analysis.area == null ? "" : `<p class="case-medical-muted">Diện tích: ${display(analysis.area)} px² · Chu vi: ${display(analysis.perimeter)} px · Tỷ lệ: ${safePercent(analysis.ratio)}</p>`}</div>`,
        )
        .join("");
      const ai = section(
        "scan",
        "Kết quả phân loại hình ảnh học DermaScan AI",
        classifications ||
          '<p class="case-medical-muted">Chưa có kết quả phân tích được lưu.</p>',
      );
      const reviews = item.reviews || [];
      const medicalNotes = reviews
        .map(
          (review) =>
            `<div class="case-medical-callout green"><span>KẾT LUẬN Y KHOA:</span><p>${display(review.conclusion)}</p><small>Ghi chú lâm sàng: ${display(review.note)}</small><small>Bác sĩ: ${display(review.doctor)}</small></div>`,
        )
        .join("");
      const doctor = section(
        "note",
        "Nhận định chẩn đoán lâm sàng của Bác sĩ",
        medicalNotes ||
          '<p class="case-medical-muted">Chưa có nhận xét chuyên môn được lưu.</p>',
      );
      const recommendations = reviews
        .map(
          (review) =>
            `<div class="case-medical-callout orange"><span>HƯỚNG ĐIỀU TRỊ / KHUYẾN NGHỊ:</span><p>${display(review.recommendation)}</p></div>`,
        )
        .join("");
      const care = section(
        "care",
        "Hướng điều trị & Khuyến nghị chăm sóc",
        recommendations ||
          '<p class="case-medical-muted">Chưa có khuyến nghị từ bác sĩ.</p>',
      );
      const images = (item.images || [])
        .map(
          (image) =>
            `<figure><img src="${image.url}" alt="Ảnh Dermoscopy" loading="lazy"/><figcaption>${display(image.filename)}</figcaption></figure>`,
        )
        .join("");
      const additionalImages = (item.analyses || [])
        .flatMap((analysis) => [
          analysis.gradcam_url
            ? `<figure><img src="${analysis.gradcam_url}" alt="Ảnh Grad-CAM" loading="lazy"/><figcaption>Grad-CAM #${analysis.id}</figcaption></figure>`
            : "",
          analysis.contour_url
            ? `<figure><img src="${analysis.contour_url}" alt="Ảnh khoanh vùng tổn thương" loading="lazy"/><figcaption>Khoanh vùng #${analysis.id}</figcaption></figure>`
            : "",
        ])
        .join("");
      const gallery =
        images || additionalImages
          ? section(
              "image",
              "Hình ảnh ca khám",
              `<div class="case-images">${images}${additionalImages}</div>`,
            )
          : "";
      $("#admin-case-detail").innerHTML =
        overview + ai + doctor + care + gallery;
    } catch (error) {
      $("#admin-case-detail").textContent = error.message;
    }
  }

  const changed = () => {
    page = 1;
    loadAdminCases();
  };
  $("#case-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(changed, 250);
  });
  ["#case-status", "#case-doctor", "#case-from", "#case-to"].forEach((field) =>
    $(field).addEventListener("change", changed),
  );
  $("#case-reset").addEventListener("click", () => {
    [
      "#case-search",
      "#case-status",
      "#case-doctor",
      "#case-from",
      "#case-to",
    ].forEach((field) => {
      $(field).value = "";
    });
    changed();
  });
  $("#case-prev").addEventListener("click", () => {
    if (page > 1) {
      page--;
      loadAdminCases();
    }
  });
  $("#case-next").addEventListener("click", () => {
    if (page < pages) {
      page++;
      loadAdminCases();
    }
  });
  $("#admin-cases-table").addEventListener("click", (event) => {
    const button = event.target.closest("[data-view-case]");
    if (button) openCaseDetail(button.dataset.viewCase);
  });
  $("#close-case-detail").addEventListener("click", () =>
    $("#admin-case-modal").classList.remove("open"),
  );
  $("#admin-case-modal").addEventListener("click", (event) => {
    if (event.target.id === "admin-case-modal")
      event.currentTarget.classList.remove("open");
  });
  window.loadAdminCases = loadAdminCases;
})();
