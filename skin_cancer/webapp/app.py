"""
DermaScan AI - Web Application (Vietnamese)
EfficientNet-B0 skin cancer classification
"""
import io
import base64
from pathlib import Path

# Database/auth bootstrap; keep python app.py working from the webapp directory.
if not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from skin_cancer.webapp.database_app import init_database
from skin_cancer.webapp.config import PROJECT_ROOT
from skin_cancer.webapp.services.access import (
    require_roles,
    visible_case_or_404,
)
from skin_cancer.webapp.services.ai_analysis import mark_analysis_failed
from skin_cancer.webapp.services.image_upload import (
    UploadTooLarge,
    read_limited_upload,
)
from skin_cancer.webapp.extensions import db, limiter
from skin_cancer.webapp.models import (
    CaseImage,
    Analysis,
    AnalysisResult,
)
import time
from datetime import datetime, timezone
from uuid import uuid4
import torch
import torch.nn as nn
import timm
import numpy as np
from PIL import Image, UnidentifiedImageError
from flask import Flask, current_app, render_template, request, jsonify, redirect, session
from flask_login import current_user, logout_user
from flask_cors import CORS
from torchvision import transforms
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

import os
from skin_cancer.webapp.services.image_quality import check_image_quality
from skin_cancer.webapp.services.uncertainty import check_uncertainty
from skin_cancer.webapp.services.result_cache import image_hash, get_cached, save_cached, is_redis_available
from skin_cancer.webapp.services.focus_region import apply_focus_region
from skin_cancer.webapp.services.onnx_inference import OnnxPredictor
from skin_cancer.webapp.tasks import analyze_task, _run_analysis

# ============================================================
# CONFIG
# ============================================================
BASE = PROJECT_ROOT / 'skin_cancer'
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

CLASSES = ['MEL', 'NV', 'BCC', 'AK', 'BKL', 'DF', 'VASC', 'SCC']
MALIGNANT = ['MEL', 'BCC', 'SCC', 'AK']

# ============================================================
# CLASS KNOWLEDGE BASE - Tiếng Việt
# ============================================================
CLASS_INFO = {
    'MEL': {
        'name_vi': 'U hắc tố (Melanoma)',
        'short_vi': 'U hắc tố',
        'is_malignant': True,
        'risk_level': 'Rất cao',
        'description': 'U hắc tố là loại ung thư da nguy hiểm nhất, xuất phát từ tế bào sản sinh sắc tố melanin. Bệnh có thể di căn nhanh sang các cơ quan khác nếu không phát hiện và điều trị kịp thời.',
        'detail': 'Nếu được phát hiện ở giai đoạn sớm (khi tổn thương còn khu trú ở lớp biểu bì), tỷ lệ sống trên 5 năm có thể lên tới 98%.',
    },
    'NV': {
        'name_vi': 'Nốt ruồi lành tính (Nevus)',
        'short_vi': 'Nốt ruồi',
        'is_malignant': False,
        'risk_level': 'Không',
        'description': 'Nốt ruồi thông thường, lành tính. Đây là tổn thương da rất phổ biến ở mọi người, hình thành do sự tập trung của các tế bào hắc tố.',
        'detail': 'Hầu hết nốt ruồi đều vô hại. Tuy nhiên nên chú ý nếu nốt ruồi có sự thay đổi bất thường (to ra, đổi màu, chảy máu).',
    },
    'BCC': {
        'name_vi': 'Ung thư tế bào đáy (Basal Cell Carcinoma)',
        'short_vi': 'UT tế bào đáy',
        'is_malignant': True,
        'risk_level': 'Trung bình - Cao',
        'description': 'Ung thư da phổ biến nhất ở người da sáng. Phát triển chậm, ít di căn xa nhưng có thể xâm lấn mô xung quanh nếu không điều trị.',
        'detail': 'Tiên lượng rất tốt nếu được điều trị sớm. Tỷ lệ tái phát thấp sau phẫu thuật cắt bỏ hoàn toàn.',
    },
    'AK': {
        'name_vi': 'Dày sừng ánh sáng (Actinic Keratosis)',
        'short_vi': 'Dày sừng ánh sáng',
        'is_malignant': True,
        'risk_level': 'Trung bình',
        'description': 'Tổn thương tiền ung thư do tiếp xúc với tia UV lâu dài. Có thể tiến triển thành ung thư tế bào vảy nếu không được điều trị.',
        'detail': 'Khoảng 5-10% trường hợp AK tiến triển thành SCC. Điều trị sớm bằng liệu pháp áp lạnh hoặc kem bôi giúp ngăn ngừa tiến triển.',
    },
    'BKL': {
        'name_vi': 'Dày sừng lành tính (Benign Keratosis)',
        'short_vi': 'Dày sừng lành',
        'is_malignant': False,
        'risk_level': 'Không',
        'description': 'Tổn thương lành tính thường gặp ở người trung niên và cao tuổi. Bề mặt sần, màu nâu hoặc đen, trông giống như bị "dán" lên da.',
        'detail': 'Không có nguy cơ ung thư. Có thể loại bỏ vì mục đích thẩm mỹ nếu gây khó chịu hoặc vướng víu.',
    },
    'DF': {
        'name_vi': 'U xơ da (Dermatofibroma)',
        'short_vi': 'U xơ da',
        'is_malignant': False,
        'risk_level': 'Không',
        'description': 'Nốt lành tính ở lớp hạ bì, thường xuất hiện ở cẳng chân hoặc cánh tay. Cứng khi sờ, có thể lõm xuống khi ấn vào.',
        'detail': 'Đây là tổn thương hoàn toàn lành tính. Không cần điều trị trừ khi có triệu chứng khó chịu.',
    },
    'VASC': {
        'name_vi': 'Tổn thương mạch máu (Vascular Lesion)',
        'short_vi': 'Tổn thương mạch',
        'is_malignant': False,
        'risk_level': 'Không',
        'description': 'Các tổn thương mạch máu lành tính như u mạch máu (hemangioma), giãn mạch (angioma), hoặc nốt ruồi đỏ (cherry angioma).',
        'detail': 'Không nguy hiểm. Chỉ cần theo dõi định kỳ và tham khảo bác sĩ nếu có thay đổi về kích thước hoặc chảy máu.',
    },
    'SCC': {
        'name_vi': 'Ung thư tế bào vảy (Squamous Cell Carcinoma)',
        'short_vi': 'UT tế bào vảy',
        'is_malignant': True,
        'risk_level': 'Cao',
        'description': 'Ung thư da ác tính phổ biến thứ hai sau BCC. Có khả năng di căn sang hạch bạch huyết và các cơ quan khác nếu không điều trị kịp thời.',
        'detail': 'Tiên lượng tốt nếu phát hiện sớm. Tỷ lệ sống trên 5 năm khoảng 95% cho giai đoạn khu trú.',
    },
}


# ============================================================
# INTERPRETATION ENGINE - Sinh thông điệp diễn giải
# ============================================================
def generate_interpretation(p_malig, pred_class, probs_dict, context=None):
    """Sinh thông điệp diễn giải bằng tiếng Việt dựa trên xác suất,
    kết hợp với ChatGPT để tạo câu trả lời tự nhiên tùy ngữ cảnh lâm sàng."""

    info = CLASS_INFO[pred_class]
    confidence = probs_dict[pred_class] * 100

    # Phân loại mức độ
    if p_malig >= 0.85:
        severity = 'urgent'
        severity_label = 'KHẨN CẤP'
        severity_note = 'Cần đi khám ngay'
    elif p_malig >= 0.65:
        severity = 'warning'
        severity_label = 'CẦN CHÚ Ý'
        severity_note = 'Nên đi khám sớm'
    elif p_malig >= 0.45:
        severity = 'caution'
        severity_label = 'THEO DÕI'
        severity_note = 'Cần theo dõi thêm'
    else:
        severity = 'normal'
        severity_label = 'LÀNH TÍNH'
        severity_note = 'Không đáng lo ngại'

    # Thử gọi OpenAI ChatGPT để tạo phản hồi tự nhiên, chuẩn mực y tế theo ngữ cảnh
    chatgpt_data = None
    try:
        from skin_cancer.webapp.services.chatgpt_service import generate_chatgpt_consultation
        chatgpt_data = generate_chatgpt_consultation(
            p_malig=p_malig,
            pred_class=pred_class,
            probs_dict=probs_dict,
            class_info=info,
            context=context,
        )
    except Exception as exc:
        app.logger.warning("ChatGPT consultation fallback to rule-based: %s", exc)

    if chatgpt_data:
        headline = chatgpt_data.get("headline", "")
        summary = chatgpt_data.get("summary", "")
        detail = chatgpt_data.get("detail", info["detail"])
        actions = chatgpt_data.get("actions", [])
        conclusion = chatgpt_data.get("conclusion", "")
        doctor_suggestion = chatgpt_data.get("doctor_suggestion")
        chatgpt_powered = True
    else:
        chatgpt_powered = False
        doctor_suggestion = None

    if not chatgpt_data:
    
        if p_malig >= 0.85:
            headline = 'Phát hiện dấu hiệu rất đáng ngờ của tổn thương ác tính'
        elif p_malig >= 0.65:
            headline = 'Có dấu hiệu nghi ngờ tổn thương ác tính'
        elif p_malig >= 0.45:
            headline = 'Tổn thương có một số đặc điểm cần theo dõi'
        else:
            headline = 'Không phát hiện dấu hiệu ung thư rõ ràng'

        # Summary chi tiết
        summary = (
            f"Mô hình phân tích hình ảnh và nhận định đây có khoảng "
            f"{confidence:.0f}% khả năng là {info['name_vi']}. "
        )

        if info['is_malignant']:
            if pred_class == 'AK':
                summary += (
                    "Đây là tổn thương tiền ung thư — tuy chưa phải ung thư "
                    "nhưng cần được xử lý sớm để tránh tiến triển thành ung thư tế bào vảy. "
                )
            else:
                summary += (
                    "Đây là tổn thương ác tính — cần được bác sĩ chuyên khoa "
                    "đánh giá và có hướng xử lý phù hợp. "
                )
        else:
            summary += (
                "Đây là tổn thương lành tính, không có dấu hiệu ung thư. "
            )

        summary += info['description']

        # Thêm so sánh với lớp thay thế nếu có
        sorted_probs = sorted(probs_dict.items(), key=lambda x: -x[1])
        if len(sorted_probs) > 1 and sorted_probs[1][1] > 0.15:
            alt_cls, alt_prob = sorted_probs[1]
            alt_info = CLASS_INFO[alt_cls]
            summary += (
                f" Ngoài ra, một số đặc điểm trên ảnh cũng có nét tương đồng với "
                f"{alt_info['name_vi']} ({alt_prob * 100:.0f}%), do đó bác sĩ có thể "
                f"cần phân biệt giữa hai tổn thương này."
            )

        # Hành động cụ thể theo mức độ
        if severity == 'urgent':
            actions = [
                'Đặt lịch khám bác sĩ chuyên khoa da liễu trong vòng 1–2 tuần tới.',
                'Chụp ảnh và ghi lại kích thước tổn thương để theo dõi sự thay đổi.',
                'Không tự ý cào, nặn hoặc bôi thuốc lên tổn thương.',
                'Mang theo kết quả phân tích này khi đi khám để bác sĩ tham khảo.',
                'Hạn chế tiếp xúc trực tiếp với ánh nắng mặt trời.',
            ]
            conclusion = (
                "Kết quả này là cảnh báo quan trọng. Việc khám sớm giúp tăng đáng kể "
                "khả năng điều trị thành công nếu tổn thương thực sự ác tính."
            )
        elif severity == 'warning':
            actions = [
                'Nên đặt lịch khám bác sĩ da liễu trong vòng 2–4 tuần.',
                'Theo dõi sự thay đổi về kích thước, màu sắc và hình dạng tổn thương.',
                'Bảo vệ vùng da bằng kem chống nắng có SPF 50+ khi ra ngoài.',
                'Tránh tiếp xúc với ánh nắng trong khoảng 10h–16h.',
                'Chụp ảnh so sánh mỗi tuần để phát hiện thay đổi sớm.',
            ]
            conclusion = (
                "Tổn thương có một số đặc điểm cần được bác sĩ kiểm tra kỹ hơn. "
                "Không nên quá lo lắng nhưng cũng không nên chủ quan."
            )
        elif severity == 'caution':
            actions = [
                'Theo dõi tổn thương trong 4–6 tuần tới.',
                'Nếu tổn thương có thay đổi bất thường, đi khám ngay.',
                'Chụp ảnh định kỳ để so sánh.',
                'Tham khảo ý kiến bác sĩ nếu cảm thấy lo lắng.',
            ]
            conclusion = (
                "Kết quả phân tích chưa đủ rõ ràng để kết luận. Cần theo dõi thêm "
                "và thăm khám nếu có bất kỳ thay đổi nào."
            )
        else:
            actions = [
                'Kiểm tra da định kỳ 6–12 tháng một lần.',
                'Sử dụng kem chống nắng hàng ngày để bảo vệ da.',
                'Chú ý nếu có nốt ruồi mới xuất hiện hoặc nốt cũ thay đổi.',
                'Duy trì lối sống lành mạnh, không hút thuốc lá.',
            ]
            conclusion = (
                "Kết quả khả quan. Tiếp tục duy trì thói quen chăm sóc da tốt "
                "và kiểm tra định kỳ để phòng ngừa."
            )

    return {
        'severity': severity,
        'severity_label': severity_label,
        'severity_note': severity_note,
        'headline': headline,
        'summary': summary,
        'detail': detail if ('detail' in locals() and isinstance(detail, str)) else info['detail'],
        'actions': actions,
        'conclusion': conclusion,
        'doctor_suggestion': doctor_suggestion if 'doctor_suggestion' in locals() else None,
        'chatgpt_powered': chatgpt_powered if 'chatgpt_powered' in locals() else False,
        'class_info': {
            'name_vi': info['name_vi'],
            'short_vi': info['short_vi'],
            'is_malignant': info['is_malignant'],
            'risk_level': info['risk_level'],
        },
    }


# ============================================================
# MODEL
# ============================================================
class SkinCancerEfficientNet(nn.Module):
    def __init__(self, backbone='efficientnet_b0', num_classes=2, dropout=0.3):
        super().__init__()
        self.backbone = timm.create_model(backbone, pretrained=False, num_classes=0)
        feat_dim = self.backbone.num_features # 1280 chiều
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(feat_dim, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, num_classes)
        )

    def forward(self, x):
        return self.head(self.backbone(x))


print(f"[BOOT] Device: {DEVICE}")
print("[BOOT] Loading binary classifier...")
model_bin = SkinCancerEfficientNet(num_classes=2, dropout=0.3).to(DEVICE)
model_bin.load_state_dict(torch.load(
    f'{BASE}/checkpoints/best_binary.pth', map_location=DEVICE))
model_bin.eval()

print("[BOOT] Loading multiclass classifier...")
model_mc = SkinCancerEfficientNet(num_classes=8, dropout=0.4).to(DEVICE)
model_mc.load_state_dict(torch.load(
    f'{BASE}/checkpoints/best_multiclass.pth', map_location=DEVICE))
model_mc.eval()
print("[BOOT] Models ready.")

preprocess = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# torch (mặc định) | onnx | onnx_int8
MODEL_BACKEND = os.environ.get("MODEL_BACKEND", "torch")
onnx_predictor = None
if MODEL_BACKEND.startswith("onnx"):
    onnx_predictor = OnnxPredictor(
        BASE / "checkpoints",
        suffix="_int8" if MODEL_BACKEND == "onnx_int8" else "",
    )
print(f"[BOOT] Backend: {MODEL_BACKEND}")

# ============================================================
# FLASK
# ============================================================
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)
init_database(app)


def to_b64(pil_img, fmt='PNG'):
    buf = io.BytesIO()
    pil_img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def arr_to_b64(arr):
    return to_b64(Image.fromarray(arr))

def utcnow_naive():
    return datetime.now(
        timezone.utc
    ).replace(tzinfo=None)

def run_ai_inference(pil_img, context=None):
    key = image_hash(pil_img)
    cached = get_cached(key)
    if cached and isinstance(cached, dict) and "result" in cached:
        result = cached["result"]
        result["meta"]["from_cache"] = True
        png = base64.b64decode(result["gradcam"])
        cam_vis = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
        return result, cam_vis, cached["inference_ms"]

    quality = check_image_quality(pil_img)
    result, cam_vis, ms = _run_model(pil_img, context=context)
    result["quality"] = quality
    result["uncertainty"] = check_uncertainty(result["multiclass"]["probs"])
    result["meta"]["from_cache"] = False

    save_cached(key, {"result": result, "inference_ms": ms})
    return result, cam_vis, ms


def _run_model(pil_img, context=None):
    """
    Chạy EfficientNet-B0 binary + multiclass + Grad-CAM.

    Hàm dùng chung cho:
    - /predict legacy
    - /api/case-images/<id>/analyze
    """

    w, h = pil_img.size

    preview = pil_img.resize(
        (420, 420),
        Image.LANCZOS,
    )

    preview_b64 = to_b64(
        preview,
        fmt="JPEG",
    )

    inp = preprocess(
        pil_img
    ).unsqueeze(0).to(DEVICE)

    start = time.perf_counter()

    if onnx_predictor:
        p_malig, probs_mc = onnx_predictor.predict(inp.cpu().numpy())
    else:
        with torch.no_grad():

            logits_bin = model_bin(inp)

            p_malig = torch.softmax(
                logits_bin,
                dim=1,
            )[0, 1].item()

            logits_mc = model_mc(inp)

            probs_mc = torch.softmax(
                logits_mc,
                dim=1,
            )[0].cpu().numpy()

    pred_idx = int(
        probs_mc.argmax()
    )

    pred_class = CLASSES[
        pred_idx
    ]

    probs_dict = {
        c: float(p)
        for c, p in zip(
            CLASSES,
            probs_mc,
        )
    }

    # ==========================================
    # GRAD-CAM
    # ==========================================

    rgb_img = (
        np.array(
            pil_img.resize(
                (224, 224)
            )
        )
        / 255.0
    )

    with GradCAM(
        model=model_mc,
        target_layers=[
            model_mc.backbone.conv_head
        ],
    ) as cam:

        gray = cam(
            input_tensor=inp,
            targets=[
                ClassifierOutputTarget(
                    pred_idx
                )
            ],
        )[0]

    cam_vis = show_cam_on_image(
        rgb_img.astype(
            np.float32
        ),
        gray,
        use_rgb=True,
    )

    # Một số version pytorch-grad-cam
    # trả uint8 0-255.
    if cam_vis.dtype != np.uint8:

        cam_vis = np.clip(
            cam_vis * 255,
            0,
            255,
        ).astype(np.uint8)

    inference_time_ms = (
        time.perf_counter()
        - start
    ) * 1000.0

    gradcam_b64 = arr_to_b64(
        cam_vis
    )

    interpretation = (
        generate_interpretation(
            p_malig,
            pred_class,
            probs_dict,
            context=context,
        )
    )

    result = {
        "success": True,

        "original": preview_b64,

        "gradcam": gradcam_b64,

        "binary": {
            "prob_malignant":
                float(p_malig),

            "prediction":
                int(p_malig > 0.5),

            "label_vi": (
                "NGHI NGỜ ÁC TÍNH"
                if p_malig > 0.5
                else "LÀNH TÍNH"
            ),

            "confidence_pct": round(
                max(
                    p_malig,
                    1 - p_malig,
                ) * 100,
                1,
            ),
        },

        "multiclass": {
            "pred_class":
                pred_class,

            "pred_conf":
                float(
                    probs_mc[
                        pred_idx
                    ]
                ),

            "probs":
                probs_dict,

            "classes":
                CLASSES,

            "malignant_list":
                MALIGNANT,

            "name_vi":
                CLASS_INFO[
                    pred_class
                ]["name_vi"],
        },

        "interpretation":
            interpretation,

        "meta": {
            "img_size":
                f"{w} x {h}",

            "device":
                DEVICE,

            "inference_time_ms":
                round(
                    inference_time_ms,
                    2,
                ),
        },
    }

    return (
        result,
        cam_vis,
        inference_time_ms,
    )

@app.route('/')
def index():
    if current_user.is_authenticated and current_user.is_active:
        destinations = {
            'ADMIN': '/admin',
            'DOCTOR': '/doctor',
            'USER': '/patient',
        }
        destination = destinations.get(current_user.role)
        if destination:
            return redirect(destination)
    return render_template('index.html')


@app.route('/doctor')
@require_roles('DOCTOR')
def doctor_portal():
    return render_template('index.html', portal_role='DOCTOR')


@app.route('/patient')
@require_roles('USER')
def patient_portal():
    return render_template('index.html', portal_role='USER')


@app.route('/logout')
def app_logout():
    try:
        if current_user.is_authenticated:
            logout_user()
    except Exception:
        pass
    session.clear()
    resp = redirect('/')
    resp.delete_cookie(app.config.get('SESSION_COOKIE_NAME', 'session'), path='/')
    resp.delete_cookie(app.config.get('REMEMBER_COOKIE_NAME', 'remember_token'), path='/')
    return resp


@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'device': DEVICE,
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    })

@app.route(
    "/predict",
    methods=["POST"],
)
@limiter.limit(
    lambda: current_app.config["RATELIMIT_EXPENSIVE"]
)
@require_roles("ADMIN", "DOCTOR")
def predict():

    try:

        if "image" not in request.files:

            return jsonify(
                {
                    "error":
                        "Chưa có ảnh "
                        "được tải lên"
                }
            ), 400

        file = request.files[
            "image"
        ]

        if not file.filename:

            return jsonify(
                {
                    "error":
                        "Tên file "
                        "không hợp lệ"
                }
            ), 400

        try:

            image_data = read_limited_upload(
                file.stream,
                int(
                    app.config[
                        "BATCH_MAX_FILE_BYTES"
                    ]
                ),
            )

            pil_img = Image.open(
                io.BytesIO(image_data)
            ).convert("RGB")

        except UploadTooLarge as exc:

            return jsonify(
                {
                    "error": str(exc)
                }
            ), 413

        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
        ):

            return jsonify(
                {
                    "error":
                        "File ảnh "
                        "không hợp lệ"
                }
            ), 400

        lesion_location = request.form.get('lesion_location', '').strip()
        data, _, _ = (
            run_ai_inference(
                pil_img, context={'lesion_location': lesion_location}
            )
        )

        return jsonify(data)

    except Exception:

        app.logger.exception(
            "Direct AI prediction failed"
        )

        return jsonify(
            {
                "error":
                    "Không thể "
                    "phân tích ảnh"
            }
        ), 500

@app.route("/api/case-images/<int:case_image_id>/analyze", methods=["POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_EXPENSIVE"])
@require_roles("ADMIN", "DOCTOR")
def analyze_case_image(case_image_id):
    """Tạo Analysis (PENDING), đẩy việc vào hàng đợi Celery rồi trả về ngay."""
    try:
        case_image = db.session.get(CaseImage, case_image_id)
        if not case_image:
            return jsonify({"error": "Không tìm thấy ảnh."}), 404

        case = visible_case_or_404(case_image.case_id)

        if not case_image.image_path or case_image.status == "FAILED":
            return jsonify({"error": "Ảnh upload không hợp lệ."}), 400

        upload_root = Path(app.config["UPLOAD_FOLDER"]).resolve()
        image_path = Path(case_image.image_path).resolve()
        if upload_root not in image_path.parents or not image_path.is_file():
            return jsonify({"error": "Không tìm thấy file ảnh."}), 404

        analysis = Analysis(case_id=case.id, case_image_id=case_image.id, status="PENDING")
        db.session.add(analysis)
        db.session.commit()

        queued = False
        if is_redis_available() and analyze_task is not None:
            try:
                analyze_task.apply_async(
                    args=[analysis.id, case_image.id],
                    task_id=f"analysis-{analysis.id}",
                )
                queued = True
            except Exception as exc:
                app.logger.info("Celery/Redis chưa bật, kích hoạt worker chạy ngầm cục bộ: %s", exc)

        if not queued:
            # Tự động chạy ngầm bằng Threading ngay trên tiến trình Flask (không cần Docker/Redis/Celery)
            import threading
            threading.Thread(
                target=_run_analysis,
                args=(analysis.id, case_image.id),
                daemon=True
            ).start()

        return jsonify({"analysis_id": analysis.id, "status": "PENDING"}), 202
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise

if __name__ == '__main__':
    print()
    print("=" * 62)
    print("  DERMASCAN AI - SERVER DANG CHAY")
    print("  Dia chi :  http://localhost:5000")
    print(f"  Thiet bi:  {DEVICE}")
    print("=" * 62)
    print()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
