/* Quản lý trang chủ: mọi chỉnh sửa giữ trên trình duyệt đến khi bấm Lưu. */
(() => {
  const root = document.getElementById("module-homepage");
  if (!root) return;
  const editor = document.getElementById("hm-editor-fields");
  const preview = document.getElementById("hm-preview");
  const status = document.getElementById("hm-status");
  const saveButton = document.getElementById("hm-save");
  const state = {
    loaded: false,
    loading: false,
    dirty: false,
    tab: "branding",
    language: "vi",
    device: "desktop",
    settings: {},
    slides: [],
    images: [],
    files: new Map(),
    urls: new Map(),
    serial: 0,
  };
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[character],
    );
  const info = (message, error = false) => {
    status.textContent = message;
    status.style.color = error ? "#bf3434" : "#248341";
  };
  const config = () => state.settings.homepage_config;
  const lang = () => config()[state.language];
  const field = (label, path, value, options = {}) =>
    `<label class="hm-field">${esc(label)}${options.long ? `<textarea data-hm-path="${esc(path)}" maxlength="${options.max || 1200}">${esc(value)}</textarea>` : `<input data-hm-path="${esc(path)}" type="${options.type || "text"}" maxlength="${options.max || 500}" value="${esc(value)}" />`}</label>`;
  const group = (title, description = "") =>
    `<h3>${esc(title)}</h3>${description ? `<p class="hm-help">${esc(description)}</p>` : ""}`;
  let openCalendar = null;
  function get(path) {
    return path
      .split(".")
      .reduce((value, key) => value?.[key], {
        settings: state.settings,
        slides: state.slides,
      });
  }
  function put(path, value) {
    const parts = path.split(".");
    let node = { settings: state.settings, slides: state.slides };
    for (const part of parts.slice(0, -1)) node = node[part];
    node[parts.at(-1)] = value;
    changed();
  }
  function changed() {
    state.dirty = true;
    info("Có thay đổi chưa lưu");
    paintPreview();
  }
  function selection(path, kind, label) {
    const value = get(path) || "";
    return `<div class="hm-image-tools"><span class="hm-field-title">${esc(label)}</span><label class="hm-file-picker"><span class="hm-upload-button"><svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V3m-5 5 5-5 5 5"/><path d="M4 16v4h16v-4"/></svg>Chọn ảnh từ máy</span><input data-hm-file="${esc(path)}" data-hm-kind="${esc({ logo: "logos", favicon: "favicons", banner: "banners" }[kind] || kind)}" type="file" accept="image/png,image/jpeg,image/webp,image/x-icon,image/vnd.microsoft.icon" aria-label="Chọn ảnh tải lên" /><span class="hm-file-name" aria-live="polite">${esc(state.files.get(path)?.file.name || (value ? "Đang sử dụng ảnh đã lưu · PNG, JPG, WEBP, ICO" : "Chưa chọn tệp · PNG, JPG, WEBP, ICO"))}</span></label><img data-hm-image="${esc(path)}" alt="Xem trước ảnh đã chọn" /><p class="hm-help">Hình mới chỉ tải lên máy chủ khi nhấn Lưu.</p></div>`;
  }
  function partsOfDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})(?:T| )(\d{2}):(\d{2})/.exec(
      value || "",
    );
    if (!match) return null;
    const [year, month, day, hour, minute] = match.slice(1).map(Number);
    const date = new Date(year, month - 1, day);
    return date.getFullYear() === year &&
      date.getMonth() === month - 1 &&
      date.getDate() === day &&
      hour < 24 &&
      minute < 60
      ? { year, month: month - 1, day, hour, minute }
      : null;
  }
  function formatDateTime(value) {
    const date = partsOfDate(value);
    return date
      ? `${String(date.day).padStart(2, "0")}/${String(date.month + 1).padStart(2, "0")}/${date.year} ${String(date.hour).padStart(2, "0")}:${String(date.minute).padStart(2, "0")}`
      : "";
  }
  function calendarMarkup(calendar) {
    const title = new Intl.DateTimeFormat("vi-VN", {
      month: "long",
      year: "numeric",
    }).format(new Date(calendar.year, calendar.month, 1));
    const first = (new Date(calendar.year, calendar.month, 1).getDay() + 6) % 7;
    const days = new Date(calendar.year, calendar.month + 1, 0).getDate();
    const cells = Array.from(
      { length: first },
      () => '<span aria-hidden="true"></span>',
    )
      .concat(
        Array.from({ length: days }, (_, index) => {
          const day = index + 1;
          const selected = day === calendar.day ? " is-selected" : "";
          return `<button type="button" class="hm-day${selected}" data-hm-day="${day}" aria-pressed="${day === calendar.day}">${day}</button>`;
        }),
      )
      .join("");
    return `<div class="hm-calendar-popover" role="group" aria-label="Chọn ngày và giờ"><div class="hm-calendar-header"><button type="button" data-hm-month="-1" aria-label="Tháng trước">‹</button><strong>${esc(title)}</strong><button type="button" data-hm-month="1" aria-label="Tháng sau">›</button></div><div class="hm-calendar-grid">${["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((day) => `<span class="hm-weekday">${day}</span>`).join("")}${cells}</div><div class="hm-calendar-time"><label>Giờ<input type="number" min="0" max="23" data-hm-hour value="${String(calendar.hour).padStart(2, "0")}" /></label><span>:</span><label>Phút<input type="number" min="0" max="59" data-hm-minute value="${String(calendar.minute).padStart(2, "0")}" /></label></div><div class="hm-calendar-actions"><button type="button" data-hm-clear>Xóa ngày</button><button type="button" class="hm-calendar-confirm" data-hm-apply>Áp dụng</button></div></div>`;
  }
  function dateTimeField(label, path, value) {
    return `<div class="hm-field hm-date-field"><span>${esc(label)}</span><button type="button" class="hm-date-trigger" data-hm-calendar="${esc(path)}" aria-expanded="${openCalendar?.path === path}" aria-label="${esc(label)}: mở lịch chọn ngày giờ"><span>${esc(formatDateTime(value) || "Chọn ngày và giờ")}</span><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/></svg></button>${openCalendar?.path === path ? calendarMarkup(openCalendar) : ""}</div>`;
  }
  function languageButtons() {
    return `<div class="hm-banner-actions"><button type="button" data-hm-lang="vi" aria-pressed="${state.language === "vi"}">Tiếng Việt ${state.language === "vi" ? "✓" : ""}</button><button type="button" data-hm-lang="en" aria-pressed="${state.language === "en"}">English ${state.language === "en" ? "✓" : ""}</button></div>`;
  }
  function banner(index, slide) {
    const prefix = `slides.${index}`;
    return `<div class="hm-banner-item"><strong>Banner ${index + 1}</strong><div class="hm-banner-actions"><button type="button" data-hm-move="${index}:-1" ${index === 0 ? "disabled" : ""}>↑ Lên</button><button type="button" data-hm-move="${index}:1" ${index === state.slides.length - 1 ? "disabled" : ""}>↓ Xuống</button><button type="button" class="danger" data-hm-remove="${index}">Xóa</button></div>${field("Tiêu đề", `${prefix}.title`, slide.title)}${field("Mô tả", `${prefix}.subtitle`, slide.subtitle, { long: true })}${selection(`${prefix}.image_path`, "banner", "Ảnh banner")}${field("Chữ nút bấm", `${prefix}.button_text`, slide.button_text)}${field("Đường dẫn nút bấm", `${prefix}.button_url`, slide.button_url)}<label class="hm-field">Hiển thị <input type="checkbox" data-hm-check="${prefix}.is_active" ${slide.is_active ? "checked" : ""}></label><div class="hm-inline">${dateTimeField("Bắt đầu (tùy chọn)", `${prefix}.start_at`, slide.start_at)}${dateTimeField("Kết thúc (tùy chọn)", `${prefix}.end_at`, slide.end_at)}</div></div>`;
  }
  function drawEditor() {
    if (!state.loaded) return;
    const s = state.settings,
      c = config(),
      l = lang();
    let body = "";
    switch (state.tab) {
      case "branding":
        body =
          group(
            "Thương hiệu",
            "Thay đổi tên, logo, favicon và mô tả trên thanh đầu trang.",
          ) +
          field("Tên website", "settings.site_name", s.site_name) +
          field(
            "Mô tả ngắn",
            "settings.footer_description",
            s.footer_description,
            { long: true },
          ) +
          selection("settings.logo_path", "logo", "Logo") +
          selection("settings.favicon_path", "favicon", "Favicon");
        break;
      case "banners":
        body =
          group(
            "Quản lý banner",
            "Thêm, xóa, sắp xếp, bật/tắt hoặc đặt thời gian hiển thị. Tối đa 20 banner.",
          ) +
          state.slides.map((item, i) => banner(i, item)).join("") +
          `<button type="button" class="hm-add-banner" data-hm-add><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg> Thêm banner</button>`;
        break;
      case "content":
        body =
          group(
            "Nội dung trang chủ",
            "Thay đổi lời kêu gọi và ba thẻ tính năng.",
          ) +
          languageButtons() +
          field(
            "Nút chính",
            `settings.homepage_config.${state.language}.hero.primary_cta`,
            l.hero.primary_cta,
          ) +
          field(
            "Nút phụ",
            `settings.homepage_config.${state.language}.hero.secondary_cta`,
            l.hero.secondary_cta,
          ) +
          field(
            "Nhãn đầu mục",
            `settings.homepage_config.${state.language}.features.eyebrow`,
            l.features.eyebrow,
          ) +
          field(
            "Tiêu đề tính năng",
            `settings.homepage_config.${state.language}.features.title`,
            l.features.title,
          ) +
          field(
            "Giới thiệu tính năng",
            `settings.homepage_config.${state.language}.features.lead`,
            l.features.lead,
            { long: true },
          ) +
          l.features.items
            .map(
              (item, i) =>
                group(`Tính năng ${i + 1}`) +
                ["badge", "title", "description"]
                  .map((key) =>
                    field(
                      { badge: "Nhãn", title: "Tiêu đề", description: "Mô tả" }[
                        key
                      ],
                      `settings.homepage_config.${state.language}.features.items.${i}.${key}`,
                      item[key],
                      { long: key === "description" },
                    ),
                  )
                  .join(""),
            )
            .join("");
        break;
      case "contact":
        body =
          group("Liên hệ và mạng xã hội") +
          field("Số điện thoại", "settings.phone", s.phone) +
          field("Email liên hệ", "settings.email", s.email) +
          field("Địa chỉ", "settings.address", s.address, { long: true }) +
          field("Facebook (HTTPS)", "settings.facebook_url", s.facebook_url) +
          Object.entries(c.social_links)
            .map(([key, value]) =>
              field(
                `${key.toUpperCase()} (HTTPS)`,
                `settings.homepage_config.social_links.${key}`,
                value,
              ),
            )
            .join("");
        break;
      case "footer":
        body =
          group(
            "Thông tin Footer",
            "Giữ nội dung cảnh báo y khoa rằng AI không thay thế tư vấn bác sĩ.",
          ) +
          field("Tên Footer", "settings.footer_title", s.footer_title) +
          field("Bản quyền", "settings.copyright_text", s.copyright_text) +
          languageButtons() +
          field(
            "Giới thiệu Footer",
            `settings.homepage_config.${state.language}.footer_extra.about`,
            l.footer_extra.about,
            { long: true },
          ) +
          l.footer_extra.technology
            .map((value, i) =>
              field(
                `Công nghệ ${i + 1}`,
                `settings.homepage_config.${state.language}.footer_extra.technology.${i}`,
                value,
              ),
            )
            .join("") +
          field(
            "Lưu ý y khoa",
            `settings.homepage_config.${state.language}.footer_extra.medical_notice`,
            l.footer_extra.medical_notice,
            { long: true },
          ) +
          field(
            "Khẩu hiệu",
            `settings.homepage_config.${state.language}.footer_extra.tagline`,
            l.footer_extra.tagline,
          );
        break;
    }
    editor.innerHTML = `<div class="hm-panel">${body}</div>`;
    editor.querySelectorAll("[data-hm-image]").forEach((img) => {
      const url = imageUrl(get(img.dataset.hmImage), img.dataset.hmImage);
      if (url) img.src = url;
      else img.hidden = true;
    });
    const calendar = editor.querySelector(".hm-calendar-popover");
    if (calendar) {
      const spaceBelow =
        window.innerHeight -
        calendar.parentElement.getBoundingClientRect().bottom;
      const spaceAbove = calendar.parentElement.getBoundingClientRect().top;
      calendar.classList.toggle(
        "hm-calendar-above",
        spaceBelow < calendar.offsetHeight + 12 && spaceAbove > spaceBelow,
      );
    }
  }
  function imageUrl(path, key) {
    if (state.urls.has(key)) return state.urls.get(key);
    return path
      ? `/api/admin/site-media/image?path=${encodeURIComponent(path)}`
      : "";
  }
  function paintPreview() {
    if (!state.loaded) return;
    const s = state.settings,
      c = config(),
      l = lang();
    const active = state.slides.find(
      (slide) =>
        slide.is_active &&
        (!slide.start_at || new Date(slide.start_at) <= new Date()) &&
        (!slide.end_at || new Date(slide.end_at) >= new Date()),
    );
    const safeText = (tag, css, text, parent) => {
      const el = document.createElement(tag);
      if (css) el.className = css;
      el.textContent = text || "";
      parent.appendChild(el);
      return el;
    };
    preview.replaceChildren();
    const head = safeText("div", "hm-site-header", "", preview);
    const logo = imageUrl(s.logo_path, "settings.logo_path");
    if (logo) {
      const image = document.createElement("img");
      image.src = logo;
      image.alt = "Logo";
      head.appendChild(image);
    }
    safeText("span", "", s.site_name, head);
    const hero = safeText("section", "hm-site-hero", "", preview);
    const heroImage =
      active &&
      imageUrl(
        active.image_path,
        `slides.${state.slides.indexOf(active)}.image_path`,
      );
    if (heroImage)
      hero.style.backgroundImage = `linear-gradient(transparent,rgba(0,0,0,.35)),url("${heroImage.replace(/"/g, "%22")}")`;
    const heroCopy = safeText("div", "hm-hero-copy", "", hero);
    safeText("h3", "", active?.title || s.site_name, heroCopy);
    safeText("p", "", active?.subtitle || s.footer_description, heroCopy);
    safeText(
      "small",
      "",
      l.hero.primary_cta + " · " + l.hero.secondary_cta,
      heroCopy,
    );
    const features = safeText("section", "hm-site-features", "", preview);
    safeText("small", "", l.features.eyebrow, features);
    safeText("h3", "", l.features.title, features);
    safeText("p", "", l.features.lead, features);
    const cards = safeText("div", "hm-feature-cards", "", features);
    l.features.items.forEach((item) => {
      const card = safeText("article", "", "", cards);
      safeText("small", "", item.badge, card);
      safeText("strong", "", item.title, card);
      safeText("p", "", item.description, card);
    });
    const foot = safeText("footer", "hm-site-footer", "", preview);
    safeText("strong", "", s.footer_title || s.site_name, foot);
    safeText("p", "", l.footer_extra.about, foot);
    safeText(
      "small",
      "",
      `${s.email || ""}  ${s.phone || ""}  ${s.address || ""}`,
      foot,
    );
    safeText("small", "", l.footer_extra.technology.join(" · "), foot);
    safeText("small", "", l.footer_extra.medical_notice, foot);
    safeText(
      "small",
      "",
      l.footer_extra.tagline + " · " + s.copyright_text,
      foot,
    );
  }
  function rerender() {
    drawEditor();
    paintPreview();
  }
  function syncFile(path, file, kind) {
    const old = state.urls.get(path);
    if (old) URL.revokeObjectURL(old);
    state.urls.delete(path);
    state.files.delete(path);
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        info("Ảnh tối đa 5 MB.", true);
        rerender();
        return;
      }
      state.files.set(path, { file, kind });
      state.urls.set(path, URL.createObjectURL(file));
      changed();
    }
    rerender();
  }
  function updateSlideFiles(transform) {
    for (const collection of [state.files, state.urls]) {
      const entries = Array.from(collection.entries());
      collection.clear();
      for (const [key, value] of entries) {
        const match = /^slides\.(\d+)\.(.*)$/.exec(key);
        if (!match) {
          collection.set(key, value);
          continue;
        }
        const index = transform(Number(match[1]));
        if (index === null) {
          if (collection === state.urls) URL.revokeObjectURL(value);
        } else collection.set(`slides.${index}.${match[2]}`, value);
      }
    }
  }
  async function request(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.method && options.method !== "GET") {
      const response = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
      });
      const token = await response.json();
      if (!response.ok || !token.csrf_token)
        throw Error("Không lấy được CSRF token.");
      headers["X-CSRFToken"] = token.csrf_token;
    }
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(data.message || `HTTP ${response.status}`);
    return data;
  }
  async function load() {
    if (state.loaded || state.loading) return;
    state.loading = true;
    info("Đang tải cấu hình...");
    try {
      const [settings, slides, media] = await Promise.all([
        request("/api/site-settings"),
        request("/api/admin/slides"),
        request("/api/admin/site-media"),
      ]);
      state.settings = settings;
      delete state.settings.id;
      delete state.settings.logo_url;
      delete state.settings.favicon_url;
      delete state.settings.updated_by;
      delete state.settings.updated_at;
      state.settings.homepage_config ||= clone(
        window.DERMASCAN_HOMEPAGE_DEFAULTS || {},
      );
      state.slides = clone(slides.slides || []);
      state.images = media.images || [];
      state.loaded = true;
      info("Đã tải cấu hình.");
      rerender();
    } catch (error) {
      info(error.message, true);
    } finally {
      state.loading = false;
    }
  }
  function normalizeSlides() {
    return state.slides.map(
      ({
        id,
        title,
        subtitle,
        image_path,
        button_text,
        button_url,
        is_active,
        start_at,
        end_at,
      }) => ({
        ...(Number.isInteger(id) ? { id } : {}),
        title,
        subtitle,
        image_path,
        button_text: button_text || null,
        button_url: button_url || null,
        is_active: !!is_active,
        start_at: start_at || null,
        end_at: end_at || null,
      }),
    );
  }
  async function save() {
    if (!state.loaded) return;
    if (
      state.slides.some(
        (slide) =>
          slide.start_at &&
          slide.end_at &&
          new Date(slide.end_at) < new Date(slide.start_at),
      )
    ) {
      info(
        "Thời gian kết thúc banner phải sau hoặc bằng thời gian bắt đầu.",
        true,
      );
      return;
    }
    saveButton.disabled = true;
    info("Đang lưu...");
    try {
      for (const [path, upload] of state.files.entries()) {
        const body = new FormData();
        body.append("kind", upload.kind);
        body.append("image", upload.file);
        const data = await request("/api/admin/site-media", {
          method: "POST",
          body,
        });
        put(path, data.path);
      }
      const data = await request("/api/admin/homepage/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          settings: state.settings,
          slides: normalizeSlides(),
        }),
      });
      state.settings = data.settings;
      ["id", "logo_url", "favicon_url", "updated_by", "updated_at"].forEach(
        (key) => delete state.settings[key],
      );
      state.slides = data.slides || [];
      state.images = (await request("/api/admin/site-media")).images || [];
      state.files.clear();
      state.urls.forEach((url) => URL.revokeObjectURL(url));
      state.urls.clear();
      state.dirty = false;
      info("Đã lưu và xuất bản thành công.");
      rerender();
    } catch (error) {
      info(`Không lưu được: ${error.message}`, true);
    } finally {
      saveButton.disabled = false;
    }
  }
  editor.addEventListener("input", (event) => {
    const input = event.target.closest("[data-hm-path]");
    if (!input || input.matches("select")) return;
    put(input.dataset.hmPath, input.value);
  });
  editor.addEventListener("input", (event) => {
    if (!openCalendar) return;
    const input = event.target;
    if (input.hasAttribute("data-hm-hour"))
      openCalendar.hour = Math.min(23, Math.max(0, Number(input.value) || 0));
    if (input.hasAttribute("data-hm-minute"))
      openCalendar.minute = Math.min(59, Math.max(0, Number(input.value) || 0));
  });
  editor.addEventListener("change", (event) => {
    const input = event.target;
    if (input.dataset.hmCheck) {
      put(input.dataset.hmCheck, input.checked);
      return;
    }
    if (input.dataset.hmFile) {
      if (input.files[0])
        syncFile(input.dataset.hmFile, input.files[0], input.dataset.hmKind);
    }
  });
  editor.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.hmCalendar) {
      const path = button.dataset.hmCalendar;
      if (openCalendar?.path === path) {
        openCalendar = null;
      } else {
        const existing = partsOfDate(get(path));
        const today = new Date();
        openCalendar = {
          path,
          ...(existing || {
            year: today.getFullYear(),
            month: today.getMonth(),
            day: today.getDate(),
            hour: 0,
            minute: 0,
          }),
        };
      }
      drawEditor();
      return;
    }
    if (openCalendar) {
      if (button.dataset.hmMonth) {
        const shifted = new Date(
          openCalendar.year,
          openCalendar.month + Number(button.dataset.hmMonth),
          1,
        );
        openCalendar.year = shifted.getFullYear();
        openCalendar.month = shifted.getMonth();
        openCalendar.day = Math.min(
          openCalendar.day,
          new Date(openCalendar.year, openCalendar.month + 1, 0).getDate(),
        );
        drawEditor();
        return;
      }
      if (button.dataset.hmDay) {
        openCalendar.day = Number(button.dataset.hmDay);
        drawEditor();
        return;
      }
      if (button.hasAttribute("data-hm-clear")) {
        put(openCalendar.path, null);
        openCalendar = null;
        drawEditor();
        return;
      }
      if (button.hasAttribute("data-hm-apply")) {
        const c = openCalendar;
        const pad = (n) => String(n).padStart(2, "0");
        put(
          c.path,
          `${c.year}-${pad(c.month + 1)}-${pad(c.day)}T${pad(c.hour)}:${pad(c.minute)}`,
        );
        openCalendar = null;
        drawEditor();
        return;
      }
    }
    if (button.dataset.hmLang) {
      state.language = button.dataset.hmLang;
      rerender();
    }
    if (button.hasAttribute("data-hm-add")) {
      if (state.slides.length >= 20) {
        info("Chỉ tối đa 20 banner.", true);
        return;
      }
      openCalendar = null;
      state.slides.push({
        title: "Banner mới",
        subtitle: "",
        image_path: "",
        button_text: null,
        button_url: null,
        is_active: true,
        start_at: null,
        end_at: null,
      });
      changed();
      rerender();
    }
    if (button.dataset.hmRemove !== undefined) {
      openCalendar = null;
      const i = Number(button.dataset.hmRemove);
      state.slides.splice(i, 1);
      updateSlideFiles((index) =>
        index === i ? null : index > i ? index - 1 : index,
      );
      changed();
      rerender();
    }
    if (button.dataset.hmMove) {
      openCalendar = null;
      const [index, delta] = button.dataset.hmMove.split(":").map(Number);
      const to = index + delta;
      if (to < 0 || to >= state.slides.length) return;
      [state.slides[index], state.slides[to]] = [
        state.slides[to],
        state.slides[index],
      ];
      updateSlideFiles((i) => (i === index ? to : i === to ? index : i));
      changed();
      rerender();
    }
  });
  editor.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && openCalendar) {
      openCalendar = null;
      drawEditor();
    }
  });
  document.addEventListener("click", (event) => {
    if (openCalendar && !event.target.closest(".hm-date-field")) {
      openCalendar = null;
      drawEditor();
    }
  });
  root.querySelectorAll("[data-hm-tab]").forEach((button) =>
    button.addEventListener("click", () => {
      openCalendar = null;
      state.tab = button.dataset.hmTab;
      root
        .querySelectorAll("[data-hm-tab]")
        .forEach((tab) => tab.classList.toggle("active", tab === button));
      drawEditor();
    }),
  );
  root.querySelectorAll("[data-hm-device]").forEach((button) =>
    button.addEventListener("click", () => {
      state.device = button.dataset.hmDevice;
      root
        .querySelectorAll("[data-hm-device]")
        .forEach((item) => item.classList.toggle("active", item === button));
      document.getElementById("hm-preview-screen").className =
        `hm-preview-screen ${state.device}`;
    }),
  );
  saveButton.addEventListener("click", save);
  window.addEventListener("beforeunload", (event) => {
    if (state.dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  window.loadHomepageManager = load;
})();
