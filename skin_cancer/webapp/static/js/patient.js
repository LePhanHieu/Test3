/**
 * DermaScan AI - Patient Portal Javascript Logic
 * Dành riêng cho giao diện Bệnh nhân (Role: USER)
 * Tách file riêng để dễ quản lý và bảo trì độc lập
 */

(function () {
  "use strict";

  // Cache CSRF token
  let patientCsrfToken = "";
  async function fetchCsrf() {
    try {
      const res = await fetch("/api/auth/csrf");
      const d = await res.json();
      patientCsrfToken = d.csrf_token;
    } catch (e) {
      console.warn("Could not fetch CSRF token:", e);
    }
  }

  // Helper DOM lookup
  function $(id) {
    return document.getElementById(id);
  }

  // Translations / mapping for skin cancer types
  const CLASS_MAP = {
    mel: { vi: "U hắc tố ác tính (Melanoma)", type: "malignant", desc: "Dạng ung thư da nguy hiểm nhất, bắt nguồn từ tế bào sinh sắc tố (melanocyte). Cần hội chẩn chuyên sâu và can thiệp kịp thời." },
    nv: { vi: "Nốt ruồi / Bớt sắc tố lành tính (Melanocytic Nevus)", type: "benign", desc: "Tổn thương lành tính phổ biến gồm các cụm tế bào sắc tố. Cần theo dõi định kỳ nếu có dấu hiệu đổi màu hoặc kích thước." },
    bcc: { vi: "Ung thư biểu mô tế bào đáy (Basal Cell Carcinoma)", type: "malignant", desc: "Dạng ung thư da phổ biến nhất, tiến triển chậm và hiếm khi di căn xa nhưng cần điều trị loại bỏ sớm." },
    akiec: { vi: "Dày sừng quang hóa / Ung thư biểu mô tại chỗ (Actinic Keratosis)", type: "malignant", desc: "Tổn thương tiền ung thư hoặc ung thư biểu mô tại chỗ do tiếp xúc lâu ngày với tia cực tím (UV)." },
    bkl: { vi: "Dày sừng lành tính (Benign Keratosis)", type: "benign", desc: "Tổn thương lành tính bao gồm dày sừng tiết bã, dày sừng dạng lichen hoặc hạt cơm sừng." },
    df: { vi: "U xơ da lành tính (Dermatofibroma)", type: "benign", desc: "Khối u da lành tính dạng cục nhỏ, chắc, thường xuất hiện ở chi dưới." },
    vasc: { vi: "Tổn thương mạch máu (Vascular Lesion)", type: "benign", desc: "Bao gồm u máu, u hạt sinh mủ hoặc giãn mao mạch. Đa phần là lành tính." },
    scc: { vi: "Ung thư biểu mô tế bào vảy (Squamous Cell Carcinoma)", type: "malignant", desc: "Dạng ung thư da bắt nguồn từ tế bào vảy ở lớp thượng bì, có khả năng xâm lấn mô xung quanh." }
  };

  // State
  let patientCases = [];
  let currentDetailCase = null;

  // Format date helper
  function formatDate(isoStr) {
    if (!isoStr) return "--";
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleDateString("vi-VN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit"
      });
    } catch (e) {
      return isoStr;
    }
  }

  // Switch independent Pages in Patient Portal (SPA Routing)
  function switchPatientPage(pageName, doScroll) {
    if (doScroll === undefined) doScroll = true;
    const validPages = ["timeline", "profile", "reports"];
    const targetPage = validPages.includes(pageName) ? pageName : "timeline";

    // 1. Sync Navbar active button (#patientNav [data-ptab])
    const navTabs = document.querySelectorAll("#patientNav [data-ptab]");
    navTabs.forEach(function(btn) {
      const isTarget = btn.getAttribute("data-ptab") === targetPage;
      btn.classList.toggle("is-active", isTarget);
    });

    // 2. Resolve all 3 page section elements
    const pageSections = {
      timeline: document.getElementById("patientTimelinePage"),
      profile: document.getElementById("patientProfilePage"),
      reports: document.getElementById("patientReportsPage")
    };

    // 3. Ẩn tất cả, chỉ hiện đúng trang target
    Object.keys(pageSections).forEach(function(key) {
      const section = pageSections[key];
      if (!section) return;
      if (key === targetPage) {
        // Xóa hidden theo 3 cách để chắc chắn override mọi CSS specificity
        section.classList.remove("hidden");
        section.removeAttribute("hidden");
        section.style.removeProperty("display"); // let CSS handle it
      } else {
        // Ẩn tuyệt đối
        section.classList.add("hidden");
        section.style.removeProperty("display");
      }
    });

    // 4. Tải dữ liệu theo trang đang hiển thị
    if (targetPage === "timeline" || targetPage === "reports") {
      void loadPatientCases();
    } else if (targetPage === "profile") {
      void loadPatientProfile();
    }

    // 5. Cuộn mượt tới đầu section (nếu yêu cầu)
    if (doScroll) {
      const activeSection = pageSections[targetPage];
      if (activeSection) {
        window.requestAnimationFrame(function() {
          activeSection.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }
    }
  }

  // Load Patient Cases from API /api/users/<user_id>/cases
  async function loadPatientCases() {
    const listContainer = $("patientTimelineList");
    const reportsTableBody = $("patientReportsTableBody");
    const countTotal = $("patientStatTotal");
    const countCompleted = $("patientStatCompleted");
    const countDoctorReviewed = $("patientStatDoctorReviewed");

    if (!listContainer) return;

    let user = window.currentUser;
    if (!user || !user.id) {
      try {
        const meRes = await fetch("/api/auth/me");
        if (meRes.ok) {
          user = await meRes.json();
          window.currentUser = user;
        }
      } catch (e) {}
    }

    if (!user || !user.id) return;

    try {
      listContainer.innerHTML = `
        <div style="text-align: center; padding: 40px; color: var(--ink-400);">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-green-600 mb-2"></div>
          <p>Đang tải dòng thời gian bệnh án...</p>
        </div>
      `;

      const res = await fetch(`/api/users/${user.id}/cases`);
      if (!res.ok) {
        throw new Error("Không thể tải danh sách ca bệnh.");
      }

      const data = await res.json();
      patientCases = Array.isArray(data.cases) ? data.cases : [];

      // Update counters
      if (countTotal) countTotal.textContent = patientCases.length;
      const completedList = patientCases.filter((c) => c.status === "COMPLETED" || c.status === "REVIEWED");
      if (countCompleted) countCompleted.textContent = completedList.length;

      // Render Timeline
      if (patientCases.length === 0) {
        listContainer.innerHTML = `
          <div class="patient-empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
            <h4>Chưa có hồ sơ khám bệnh nào</h4>
            <p>Khi bác sĩ thực hiện kiểm tra da và phân tích kết quả chẩn đoán cho bạn, lịch sử và phác đồ điều trị sẽ xuất hiện tại đây.</p>
          </div>
        `;
      } else {
        listContainer.innerHTML = "";
        patientCases.forEach((c) => {
          const item = document.createElement("div");
          item.className = `patient-timeline-item status-${String(c.status || "created").toLowerCase()}`;
          
          let statusLabel = "Mới tạo";
          let statusPillClass = "created";
          if (c.status === "COMPLETED") {
            statusLabel = "Đã hoàn tất";
            statusPillClass = "completed";
          } else if (c.status === "REVIEWED") {
            statusLabel = "Bác sĩ đã kết luận";
            statusPillClass = "reviewed";
          } else if (c.status === "ANALYZED") {
            statusLabel = "Đã phân tích AI";
            statusPillClass = "analyzed";
          }

          const lesionLoc = c.lesion_location || "Vị trí da chưa chỉ định cụ thể";
          const createdDate = formatDate(c.created_at);

          item.innerHTML = `
            <div class="patient-timeline-header">
              <span class="patient-case-code">${c.case_code || "CASE-#" + c.id}</span>
              <span class="patient-case-date">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></polyline>
                  <line x1="16" y1="2" x2="16" y2="6"></line>
                  <line x1="8" y1="2" x2="8" y2="6"></line>
                  <line x1="3" y1="10" x2="21" y2="10"></line>
                </svg>
                ${createdDate}
              </span>
            </div>
            <div class="patient-timeline-body">
              <div class="patient-timeline-meta">
                <span class="patient-lesion-location">${lesionLoc}</span>
                <span class="patient-doctor-info">Bác sĩ phụ trách: <strong>${c.doctor_name || "Bác sĩ chuyên khoa DermaScan"}</strong></span>
              </div>
              <div style="display: flex; align-items: center; gap: 12px;">
                <span class="patient-status-pill ${statusPillClass}">${statusLabel}</span>
                <button type="button" class="patient-action-link" data-case-id="${c.id}">
                  Chi tiết chẩn đoán
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;">
                    <path d="M5 12h14M12 5l7 7-7 7"/>
                  </svg>
                </button>
              </div>
            </div>
          `;

          item.addEventListener("click", () => {
            void openCaseDetailModal(c.id);
          });

          listContainer.appendChild(item);
        });
      }

      // Render Reports View
      if (reportsTableBody) {
        reportsTableBody.innerHTML = "";
        let totalReportsCount = 0;

        // Iterate cases and find reports
        for (const c of patientCases) {
          // If reports exist or case is completed
          const caseReports = Array.isArray(c.reports) ? c.reports : [];
          if (caseReports.length > 0) {
            caseReports.forEach((rep) => {
              totalReportsCount++;
              const tr = document.createElement("tr");
              tr.innerHTML = `
                <td><strong>${c.case_code || "CASE-#" + c.id}</strong></td>
                <td>${formatDate(rep.created_at || c.created_at)}</td>
                <td>Báo cáo chẩn đoán v${rep.report_version || 1}</td>
                <td><span class="patient-status-pill completed">Sẵn sàng</span></td>
                <td>
                  <a href="${rep.download_url}" target="_blank" class="patient-download-btn">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/>
                      <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Tải PDF
                  </a>
                </td>
              `;
              reportsTableBody.appendChild(tr);
            });
          }
        }

        if (totalReportsCount === 0) {
          reportsTableBody.innerHTML = `
            <tr>
              <td colspan="5" style="text-align: center; color: var(--ink-400); padding: 40px;">
                Chưa có file báo cáo PDF nào được xuất bản cho các ca khám của bạn.
              </td>
            </tr>
          `;
        }
      }
    } catch (err) {
      console.error(err);
      if (listContainer) {
        listContainer.innerHTML = `
          <div style="text-align: center; color: #dc2626; padding: 30px;">
            <p>Đã xảy ra lỗi khi tải hồ sơ bệnh án: ${err.message}</p>
          </div>
        `;
      }
    }
  }

  // Open Case Detail Modal (Tổn thương da, AI kết quả, Bác sĩ nhận định, Hướng điều trị)
  async function openCaseDetailModal(caseId) {
    const modal = $("patientCaseDetailModal");
    if (!modal) return;

    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";

    // Set loading placeholder
    $("patientModalCaseCode").textContent = "Đang tải...";
    $("patientModalDate").textContent = "";
    $("patientDetailContent").innerHTML = `
      <div style="text-align: center; padding: 60px; color: var(--ink-500);">
        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-green-600 mb-3"></div>
        <p>Đang tải chi tiết hồ sơ chẩn đoán...</p>
      </div>
    `;

    try {
      const res = await fetch(`/api/cases/${caseId}`);
      if (!res.ok) throw new Error("Không thể tải thông tin ca khám.");
      const c = await res.json();
      currentDetailCase = c;

      $("patientModalCaseCode").textContent = c.case_code || `CASE #${c.id}`;
      $("patientModalDate").textContent = formatDate(c.created_at);

      // Extract details
      const lesionLoc = c.lesion_location || "Vùng da kiểm tra";
      const analyses = Array.isArray(c.analyses) ? c.analyses : [];
      const latestAnalysis = analyses.length > 0 ? analyses[analyses.length - 1] : null;
      const reviews = Array.isArray(c.reviews) ? c.reviews : [];
      const latestReview = reviews.length > 0 ? reviews[reviews.length - 1] : null;
      const reports = Array.isArray(c.reports) ? c.reports : [];

      // AI Result Parsing
      let aiPredictionText = "Chưa có kết quả AI";
      let aiProbText = "--";
      let aiClassKey = "benign";
      let aiTypeLabel = "Lành tính";
      let aiDesc = "Kết quả kiểm tra AI chưa ghi nhận tổn thương nguy hiểm.";

      if (latestAnalysis && latestAnalysis.results && latestAnalysis.results.length > 0) {
        const r = latestAnalysis.results[0];
        const isMalignant = r.binary_result === 1;
        aiClassKey = isMalignant ? "malignant" : "benign";
        aiTypeLabel = isMalignant ? "Ác tính / Cần lưu ý" : "Lành tính";

        const predClass = String(r.predicted_class || "").toLowerCase();
        const mapped = CLASS_MAP[predClass];
        if (mapped) {
          aiPredictionText = mapped.vi;
          aiDesc = mapped.desc;
        } else {
          aiPredictionText = r.predicted_class || "Phân loại tế bào da";
        }

        const prob = r.predicted_probability != null ? (r.predicted_probability * 100).toFixed(1) : null;
        if (prob) aiProbText = `${prob}%`;
      }

      // Doctor Review
      const conclusion = (latestReview && latestReview.doctor_conclusion) || "Bác sĩ đang xem xét và hoàn tất kết luận chuyên khoa.";
      const clinicalNote = (latestReview && latestReview.clinical_note) || "Hình ảnh tổn thương đang trong quá trình theo dõi.";
      const recommendation = (latestReview && latestReview.recommendation) || "Tuân thủ hướng dẫn vệ sinh da, tránh tiếp xúc trực tiếp tia UV và tái khám định kỳ theo lịch hẹn.";
      const doctorName = c.doctor_name || "Bác sĩ chuyên khoa DermaScan AI";

      // Report download button if available
      let downloadButtonHtml = "";
      if (reports.length > 0) {
        const rep = reports[0];
        downloadButtonHtml = `
          <div style="margin-top: 14px;">
            <a href="${rep.download_url}" target="_blank" class="patient-download-btn" style="padding: 10px 18px; font-size: 13.5px;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Tải toàn bộ Báo cáo Y khoa PDF (v${rep.report_version})
            </a>
          </div>
        `;
      }

      // Render Modal Body
      $("patientDetailContent").innerHTML = `
        <!-- Nhóm 1: Thông tin vùng tổn thương & Bác sĩ phụ trách -->
        <div class="patient-detail-group">
          <h4 class="patient-detail-group-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
            Thông tin ca khám & Bác sĩ phụ trách
          </h4>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; font-size: 14px;">
            <div><span style="color: var(--ink-400);">Vị trí tổn thương:</span> <strong style="color: #0f172a;">${lesionLoc}</strong></div>
            <div><span style="color: var(--ink-400);">Bác sĩ chẩn đoán:</span> <strong style="color: #2ba149;">${doctorName}</strong></div>
            <div><span style="color: var(--ink-400);">Trạng thái ca:</span> <strong>${c.status || "COMPLETED"}</strong></div>
          </div>
        </div>

        <!-- Nhóm 2: Kết quả phân tích mô hình trí tuệ nhân tạo (AI) -->
        <div class="patient-detail-group">
          <h4 class="patient-detail-group-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            Kết quả phân loại hình ảnh học DermaScan AI
          </h4>
          <div>
            <div class="patient-ai-badge ${aiClassKey}">
              <span>Phân loại AI: ${aiTypeLabel}</span>
              ${aiProbText !== "--" ? `<span>· Độ tin cậy: ${aiProbText}</span>` : ""}
            </div>
            <p style="font-size: 14.5px; font-weight: 600; color: #0f172a; margin: 0 0 6px;">
              ${aiPredictionText}
            </p>
            <p style="font-size: 13.5px; color: var(--ink-500); line-height: 1.5; margin: 0;">
              ${aiDesc}
            </p>
          </div>
        </div>

        <!-- Nhóm 3: Nhận định chuyên khoa từ Bác sĩ điều trị -->
        <div class="patient-detail-group">
          <h4 class="patient-detail-group-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
            </svg>
            Nhận định chẩn đoán lâm sàng của Bác sĩ
          </h4>
          <div class="patient-doctor-callout">
            <p style="font-size: 13px; font-weight: 600; color: #2ba149; margin: 0 0 4px;">KẾT LUẬN Y KHOA:</p>
            <p style="font-size: 14.5px; color: #0f172a; font-weight: 500; margin: 0 0 10px;">${conclusion}</p>
            <p style="font-size: 13px; color: var(--ink-500); margin: 0;">
              <strong>Ghi chú lâm sàng:</strong> ${clinicalNote}
            </p>
          </div>
        </div>

        <!-- Nhóm 4: Hướng điều trị & Phác đồ dùng thuốc -->
        <div class="patient-detail-group">
          <h4 class="patient-detail-group-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
              <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
            </svg>
            Hướng điều trị & Khuyến nghị chăm sóc
          </h4>
          <div class="patient-treatment-callout">
            <p style="font-size: 13px; font-weight: 600; color: #fd8624; margin: 0 0 4px;">PHÁC ĐỒ / HƯỚNG DẪN DÙNG THUỐC:</p>
            <p style="font-size: 14.5px; color: #0f172a; line-height: 1.6; margin: 0; white-space: pre-line;">${recommendation}</p>
          </div>
          ${downloadButtonHtml}
        </div>
      `;
    } catch (e) {
      console.error(e);
      $("patientDetailContent").innerHTML = `
        <div style="text-align: center; color: #dc2626; padding: 40px;">
          <p>Không thể tải chi tiết ca bệnh: ${e.message}</p>
        </div>
      `;
    }
  }

  function closeCaseDetailModal() {
    const modal = $("patientCaseDetailModal");
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.style.overflow = "";
    currentDetailCase = null;
  }

  // Load Patient Profile into Form
  async function loadPatientProfile() {
    let user = window.currentUser;
    try {
      const res = await fetch("/api/auth/me");
      if (res.ok) {
        user = await res.json();
        window.currentUser = user;
      }
    } catch (e) {}

    if (!user) return;

    if ($("patientProfileName")) $("patientProfileName").value = user.full_name || "";
    if ($("patientProfileEmail")) $("patientProfileEmail").value = user.email || "";
    if ($("patientProfilePhone")) $("patientProfilePhone").value = user.phone || "";
    if ($("patientProfileGender")) $("patientProfileGender").value = user.gender || "Nam";
    if ($("patientProfileDob")) $("patientProfileDob").value = user.date_of_birth || "";

    // Header greetings
    if ($("patientBannerName")) $("patientBannerName").textContent = user.full_name || user.email || "Bệnh nhân";
  }

  // Save Patient Profile
  async function savePatientProfile(e) {
    if (e) e.preventDefault();
    await fetchCsrf();

    const fullName = $("patientProfileName") ? $("patientProfileName").value.trim() : "";
    const phone = $("patientProfilePhone") ? $("patientProfilePhone").value.trim() : "";
    const gender = $("patientProfileGender") ? $("patientProfileGender").value : "";
    const dob = $("patientProfileDob") ? $("patientProfileDob").value : "";

    const alertBox = $("patientProfileAlert");
    if (alertBox) alertBox.classList.add("hidden");

    try {
      const res = await fetch("/api/auth/profile", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": patientCsrfToken
        },
        body: JSON.stringify({
          full_name: fullName,
          phone: phone,
          gender: gender,
          date_of_birth: dob || null
        })
      });

      const d = await res.json();
      if (!res.ok || !d.success) {
        throw new Error(d.message || "Không thể cập nhật hồ sơ cá nhân.");
      }

      // Update current user state
      if (d.user) {
        window.currentUser = Object.assign(window.currentUser || {}, d.user);
        if ($("hpUserName")) $("hpUserName").textContent = d.user.full_name;
        if ($("hpUserAvatar")) $("hpUserAvatar").textContent = (d.user.full_name.trim().charAt(0) || "P").toUpperCase();
        if ($("patientBannerName")) $("patientBannerName").textContent = d.user.full_name;
      }

      if (alertBox) {
        alertBox.textContent = "Cập nhật thông tin cá nhân thành công!";
        alertBox.className = "p-3 rounded-xl mb-4 text-sm font-medium bg-green-50 text-green-700 border border-green-200";
        alertBox.classList.remove("hidden");
        setTimeout(() => alertBox.classList.add("hidden"), 4000);
      }
    } catch (err) {
      if (alertBox) {
        alertBox.textContent = err.message;
        alertBox.className = "p-3 rounded-xl mb-4 text-sm font-medium bg-red-50 text-red-700 border border-red-200";
        alertBox.classList.remove("hidden");
      }
    }
  }

  // Initialize event bindings for Patient Portal
  function initPatientPortal() {
    fetchCsrf();

    // Navbar tab buttons click (#patientNav [data-ptab])
    // Also handle legacy .patient-portal-tab if any
    const allTabSelectors = [
      "#patientNav [data-ptab]",
      ".patient-portal-tab[data-ptab]",
      ".patient-portal-tab[data-tab]"
    ];
    allTabSelectors.forEach(function(selector) {
      document.querySelectorAll(selector).forEach(function(tab) {
        // Prevent duplicate listeners
        if (tab.dataset._ptabBound) return;
        tab.dataset._ptabBound = "1";
        tab.addEventListener("click", function() {
          const target = tab.getAttribute("data-ptab") || tab.getAttribute("data-tab");
          if (target) switchPatientPage(target, true);
        });
      });
    });

    // Profile form submit
    const form = $("patientProfileForm");
    if (form) {
      form.addEventListener("submit", savePatientProfile);
    }

    // Modal close listeners
    const modalCloseBtn = $("patientModalCloseBtn");
    const modalBackdrop = $("patientModalBackdrop");
    if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeCaseDetailModal);
    if (modalBackdrop) modalBackdrop.addEventListener("click", closeCaseDetailModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeCaseDetailModal();
    });

    // Make functions accessible globally if needed
    window.openCaseDetailModal = openCaseDetailModal;
    window.closeCaseDetailModal = closeCaseDetailModal;
    window.loadPatientCases = loadPatientCases;
    window.loadPatientProfile = loadPatientProfile;
    window.switchPatientPage = switchPatientPage;
    window.switchPatientTab = switchPatientPage; // Compatibility fallback
  }

  // Auto-init on DOM loaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPatientPortal);
  } else {
    initPatientPortal();
  }
})();
