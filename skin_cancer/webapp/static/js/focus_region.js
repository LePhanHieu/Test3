// Task 1: Modal cho bác sĩ vẽ polygon khoanh vùng tổn thương.
//
// openFocusRegionModal(file, oldPoints) trả về Promise:
//   - mảng điểm [[x, y], ...] (toạ độ 0..1) nếu bấm "Lưu vùng"
//   - mảng rỗng []              nếu bấm "Xóa vùng đã lưu"
//   - null                      nếu bấm "Hủy"

function openFocusRegionModal(file, oldPoints) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();

    img.onload = () => {
      // Co ảnh cho vừa màn hình, giữ nguyên tỉ lệ
      const scale = Math.min(
        700 / img.width,
        (window.innerHeight * 0.65) / img.height,
        1,
      );
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.style.cssText =
        "cursor:crosshair;display:block;border-radius:6px;";
      const ctx = canvas.getContext("2d");

      // Điểm lưu theo pixel canvas, đổi sang 0..1 khi trả về
      let points = (oldPoints || []).map(([x, y]) => [
        x * canvas.width,
        y * canvas.height,
      ]);

      function draw() {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        if (points.length >= 2) {
          ctx.beginPath();
          points.forEach(([x, y], i) =>
            i ? ctx.lineTo(x, y) : ctx.moveTo(x, y),
          );
          if (points.length >= 3) {
            ctx.closePath();
            ctx.fillStyle = "rgba(255, 200, 0, 0.25)";
            ctx.fill();
          }
          ctx.strokeStyle = "#ffc800";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        points.forEach(([x, y]) => {
          ctx.beginPath();
          ctx.arc(x, y, 4, 0, Math.PI * 2);
          ctx.fillStyle = "#ff3b30";
          ctx.fill();
        });
        saveBtn.disabled = points.length < 3;
      }

      canvas.addEventListener("click", (e) => {
        const rect = canvas.getBoundingClientRect();
        points.push([e.clientX - rect.left, e.clientY - rect.top]);
        draw();
      });

      // ----- giao diện modal -----
      const overlay = document.createElement("div");
      overlay.style.cssText =
        "position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;" +
        "display:flex;align-items:center;justify-content:center;";
      const box = document.createElement("div");
      box.style.cssText =
        "background:#fff;padding:16px;border-radius:10px;max-width:95vw;";

      const hint = document.createElement("p");
      hint.textContent =
        "Bấm lên ảnh để chấm các điểm quanh vùng tổn thương (tối thiểu 3 điểm).";
      hint.style.cssText = "margin:0 0 8px;font-size:14px;";

      const bar = document.createElement("div");
      bar.style.cssText =
        "display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;";

      function makeButton(text, onClick) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = text;
        b.className = "workflow-small-btn";
        b.addEventListener("click", onClick);
        bar.append(b);
        return b;
      }

      function close(result) {
        URL.revokeObjectURL(url);
        overlay.remove();
        resolve(result);
      }

      makeButton("Hoàn tác điểm cuối", () => {
        points.pop();
        draw();
      });
      makeButton("Vẽ lại", () => {
        points = [];
        draw();
      });
      makeButton("Xóa vùng đã lưu", () => close([]));
      makeButton("Hủy", () => close(null));
      const saveBtn = makeButton("Lưu vùng", () =>
        close(points.map(([x, y]) => [x / canvas.width, y / canvas.height])),
      );
      saveBtn.classList.add("primary");

      box.append(hint, canvas, bar);
      overlay.append(box);
      document.body.append(overlay);
      draw();
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    img.src = url;
  });
}
