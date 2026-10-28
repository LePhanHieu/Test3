"""
Dịch vụ tích hợp OpenAI ChatGPT để sinh diễn giải chẩn đoán y khoa tự nhiên và thông minh.
Hệ thống kết hợp kết quả phân tích AI (EfficientNet + Grad-CAM) cùng ngữ cảnh ca bệnh
(vị trí tổn thương, thông tin bệnh nhân, tiền sử) để tạo tư vấn chuyên sâu, không bị fix cứng.
"""

import os
import json
import logging
from typing import Optional, Dict, Any

from openai import OpenAI

logger = logging.getLogger(__name__)

def get_openai_client() -> Optional[OpenAI]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key, timeout=15.0)
    except Exception as exc:
        logger.warning("Không thể khởi tạo OpenAI client: %s", exc)
        return None


def generate_chatgpt_consultation(
    p_malig: float,
    pred_class: str,
    probs_dict: Dict[str, float],
    class_info: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Gửi kết quả chẩn đoán cùng ngữ cảnh cho ChatGPT để sinh phản hồi tự nhiên,
    thấu cảm và chuẩn xác theo bối cảnh lâm sàng thực tế.
    """
    client = get_openai_client()
    if client is None:
        return None

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    context = context or {}
    lesion_location = context.get("lesion_location") or "Chưa chỉ định cụ thể"
    patient = context.get("patient") or {}

    patient_summary_parts = []
    if isinstance(patient, dict):
        if patient.get("full_name"):
            patient_summary_parts.append(f"Họ tên: {patient['full_name']}")
        if patient.get("age"):
            patient_summary_parts.append(f"Tuổi: {patient['age']}")
        elif patient.get("dob"):
            patient_summary_parts.append(f"Ngày sinh: {patient['dob']}")
        if patient.get("gender"):
            patient_summary_parts.append(f"Giới tính: {patient['gender']}")
        if patient.get("medical_history"):
            patient_summary_parts.append(f"Tiền sử bệnh: {patient['medical_history']}")
        if patient.get("notes"):
            patient_summary_parts.append(f"Ghi chú: {patient['notes']}")

    patient_desc = (
        ", ".join(patient_summary_parts)
        if patient_summary_parts
        else "Thông tin cơ bản tiêu chuẩn"
    )

    # Lấy top 3 chẩn đoán phân biệt
    sorted_probs = sorted(probs_dict.items(), key=lambda x: -x[1])
    top_diffs = []
    for cls_name, prob in sorted_probs[:3]:
        top_diffs.append(f"- {cls_name}: {prob * 100:.1f}%")
    diff_str = "\n".join(top_diffs)

    system_prompt = (
        "Bạn là Chuyên gia Da liễu AI & Cố vấn Y khoa thông minh của hệ thống DermaScan AI. "
        "Nhiệm vụ của bạn là nhận kết quả chẩn đoán tổn thương da từ mô hình thị giác máy tính "
        "kèm thông tin ngữ cảnh ca bệnh, sau đó diễn giải kết quả bằng tiếng Việt tự nhiên, "
        "sâu sắc, mang tính nhân văn và chuẩn mực y khoa, tuyệt đối KHÔNG trả lời theo khuôn mẫu dập khuôn cứng nhắc.\n\n"
        "YÊU CẦU ĐẦU RA: Trả về ĐÚNG ĐỊNH DẠNG JSON với các trường sau:\n"
        "{\n"
        '  "headline": "Tiêu đề diễn giải ngắn gọn, tự nhiên, nêu bật bản chất và vị trí tổn thương (1 câu)",\n'
        '  "summary": "Đoạn văn nhận định tổng quan tự nhiên, giải thích rõ xác suất dự đoán, tình trạng nghi ngờ hay lành tính dựa trên vị trí tổn thương và ngữ cảnh bệnh nhân (2-3 câu)",\n'
        '  "detail": "Đoạn văn phân tích bệnh học lâm sàng sâu hơn: cơ chế tổn thương, đặc điểm thường gặp, ý nghĩa đối với vị trí cụ thể trên cơ thể và khả năng phân biệt với các bệnh khác",\n'
        '  "actions": ["Khuyến nghị hành động 1", "Khuyến nghị hành động 2", "Khuyến nghị hành động 3", "Khuyến nghị hành động 4"],\n'
        '  "conclusion": "Lời dặn dò kết luận ấm áp, chuẩn xác từ chuyên gia y tế, vừa định hướng vừa giảm bớt lo lắng không cần thiết cho người bệnh",\n'
        '  "doctor_suggestion": {\n'
        '    "clinical_note": "Gợi ý tóm tắt triệu chứng và dấu hiệu lâm sàng để bác sĩ ghi vào hồ sơ bệnh án",\n'
        '    "doctor_conclusion": "Gợi ý kết luận chẩn đoán chuyên môn",\n'
        '    "recommendation": "Gợi ý phác đồ xử trí hoặc chỉ định tiếp theo (ví dụ: dermoscopy lại sau 3 tháng, sinh thiết trọn, xét nghiệm bổ sung)"\n'
        "  }\n"
        "}"
    )

    user_prompt = (
        f"KẾT QUẢ PHÂN TÍCH HÌNH ẢNH DERMOSCOPY TỪ DERMASCAN AI:\n"
        f"- Chẩn đoán dự đoán: {class_info.get('name_vi', pred_class)} ({pred_class})\n"
        f"- Phân loại mức độ: {'ÁC TÍNH' if class_info.get('is_malignant') else 'LÀNH TÍNH'}\n"
        f"- Độ tin cậy của mô hình: {probs_dict.get(pred_class, 0.5) * 100:.1f}%\n"
        f"- Xác suất ác tính tổng thể (p_malig): {p_malig * 100:.1f}%\n"
        f"- Mức độ rủi ro hệ thống: {class_info.get('risk_level', 'Theo dõi')}\n"
        f"- Phân bố xác suất các nhóm:\n{diff_str}\n\n"
        f"NGỮ CẢNH CA BỆNH THỰC TẾ:\n"
        f"- Vị trí tổn thương: {lesion_location}\n"
        f"- Thông tin bệnh nhân: {patient_desc}\n\n"
        f"Hãy tạo lời diễn giải và tư vấn tự nhiên, chuẩn mực y khoa, gắn liền với vị trí {lesion_location}."
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=900,
        )

        content = response.choices[0].message.content
        data = json.loads(content)

        # Đảm bảo các trường cần thiết có mặt và chuẩn kiểu dữ liệu
        if not isinstance(data.get("headline"), str):
            data["headline"] = f"Phân tích tổn thương da {class_info.get('name_vi', pred_class)}"
        if not isinstance(data.get("summary"), str):
            data["summary"] = f"Mô hình nhận định khả năng cao là {class_info.get('name_vi', pred_class)} tại {lesion_location}."
        if not isinstance(data.get("detail"), str):
            if isinstance(data.get("detail"), (dict, list)):
                data["detail"] = json.dumps(data["detail"], ensure_ascii=False)
            else:
                data["detail"] = class_info.get("detail", "")
        if not isinstance(data.get("actions"), list) or not data["actions"]:
            data["actions"] = [
                f"Thăm khám bác sĩ chuyên khoa da liễu để kiểm tra vùng {lesion_location}.",
                "Không tự ý nặn, gãi hoặc bôi hóa chất lạ lên tổn thương.",
                "Theo dõi các thay đổi về kích thước, màu sắc hoặc cảm giác ngứa, rát.",
                "Sử dụng kem chống nắng và bảo vệ da khi ra ngoài.",
            ]
        if not isinstance(data.get("conclusion"), str):
            data["conclusion"] = (
                "Kết quả phân tích từ AI là công cụ hỗ trợ quan trọng giúp định hướng thăm khám sớm."
            )

        data["chatgpt_powered"] = True
        return data

    except Exception as exc:
        logger.warning("Lỗi khi gọi ChatGPT consultation: %s", exc)
        return None
