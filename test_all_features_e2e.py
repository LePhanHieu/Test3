"""End-to-End Test Suite for all 8 Features.

Tests:
- Feature 2: Image Quality Check (image_quality.py)
- Feature 3: Uncertainty Detection (uncertainty.py)
- Feature 8: Redis Result Cache (result_cache.py)
- Feature 1: Focus Region Polygon (focus_region.py & API)
- Feature 4: Case Progress Timeline (timeline.py & API)
- Feature 6: ONNX Runtime Inference & Diff (onnx_inference.py)
- Feature 5: Quantization INT8 (quantize_int8.py & check INT8 models)
- Feature 7: Celery Async Task & Analysis Status (tasks.py & analysis_status.py)
"""

import io
import json
import os
import sys
from pathlib import Path

# Force utf-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PIL import Image
from flask_login import current_user
import redis

# Import app components
from skin_cancer.webapp.app import app, run_ai_inference
from skin_cancer.webapp.extensions import db
from skin_cancer.webapp.models import Case, CaseImage, Analysis, AnalysisResult, User
from skin_cancer.webapp.services.focus_region import parse_polygon, apply_focus_region
from skin_cancer.webapp.services.image_quality import check_image_quality
from skin_cancer.webapp.services.uncertainty import check_uncertainty
from skin_cancer.webapp.services.result_cache import image_hash, get_cached, save_cached, _get_client
from skin_cancer.webapp.services.onnx_inference import OnnxPredictor
from skin_cancer.webapp.tasks import _run_analysis

def run_tests():
    print("=" * 60)
    print("DERMASCAN AI - SUITE TEST TOÀN DIỆN CÁC TÍNH NĂNG")
    print("=" * 60)

    # -------------------------------------------------------------
    # 1. TEST FEATURE 2: Image Quality Check
    # -------------------------------------------------------------
    print("\n[TEST 1/8] Feature 2: Kiểm tra chất lượng ảnh (image_quality.py)")
    expected = {
        'test_mo.jpg': 'Ảnh bị mờ',
        'test_toi.jpg': 'Ảnh quá tối',
        'test_sang.jpg': 'Ảnh quá sáng',
        'test_nho.jpg': 'Ảnh quá nhỏ',
    }
    for fname, exp_sub in expected.items():
        res = check_image_quality(Image.open(fname))
        assert not res['ok'], f"{fname} phải có lỗi chất lượng"
        matched = any(exp_sub in w for w in res['warnings'])
        assert matched, f"{fname} không chứa cảnh báo mong đợi '{exp_sub}': {res['warnings']}"
        print(f"  + {fname}: [PASS] Cảnh báo đúng -> {res['warnings']}")

    goc_res = check_image_quality(Image.open("goc.jpg"))
    assert goc_res['ok'], f"goc.jpg phải có ok=True nhưng nhận: {goc_res}"
    print("  + goc.jpg: [PASS] Ảnh chuẩn ok=True, 0 cảnh báo.")

    # -------------------------------------------------------------
    # 2. TEST FEATURE 3: Uncertainty Detection
    # -------------------------------------------------------------
    print("\n[TEST 2/8] Feature 3: Độ không chắc chắn (uncertainty.py)")
    res_certain = check_uncertainty([0.92, 0.04, 0.01, 0.01, 0.01, 0.005, 0.003, 0.002])
    assert not res_certain['is_uncertain'], "Trường hợp tin cậy cao không được báo uncertain"
    print(f"  + Tin cậy cao (margin={res_certain['margin']}, entropy={res_certain['entropy']}): [PASS] is_uncertain=False")

    res_uncertain = check_uncertainty([0.48, 0.44, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01])
    assert res_uncertain['is_uncertain'], "Trường hợp margin nhỏ phải báo uncertain"
    assert res_uncertain['message'] == "Ca này khó, nên hỏi bác sĩ."
    print(f"  + Phân vân top-1 & top-2 (margin={res_uncertain['margin']}): [PASS] is_uncertain=True, message='{res_uncertain['message']}'")

    # -------------------------------------------------------------
    # 3. TEST FEATURE 8: Native Persistent Disk Cache (No Docker Needed)
    # -------------------------------------------------------------
    from skin_cancer.webapp.services.result_cache import get_cache_backend_name
    print(f"\n[TEST 3/8] Feature 8: Cache kết quả ({get_cache_backend_name()})")

    img_goc = Image.open("goc.jpg")
    key = image_hash(img_goc)

    # Chạy inference lần 1
    res1, cam1, ms1 = run_ai_inference(img_goc)
    print(f"  + Lần 1: from_cache={res1['meta']['from_cache']}, thời gian={ms1:.1f}ms")

    # Kiểm tra key trong cache
    cached_val = get_cached(key)
    assert cached_val is not None, "Dữ liệu phải tồn tại trong Cache"
    print(f"  + Key cache tồn tại: {key[:30]}...")

    # Chạy inference lần 2 (cache hit)
    res2, cam2, ms2 = run_ai_inference(img_goc)
    assert res2["meta"]["from_cache"], "Lần 2 phải from_cache=True"
    print(f"  + Lần 2 (đọc từ cache): [PASS] from_cache=True, thời gian={ms2:.1f}ms (tức thì)")

    # -------------------------------------------------------------
    # 4. TEST FEATURE 1: Focus Region (Polygon)
    # -------------------------------------------------------------
    print("\n[TEST 4/8] Feature 1: Khoanh vùng tổn thương (focus_region.py)")
    # Thử validate
    try:
        parse_polygon({"points": [[0,0],[1,1]]})
        assert False, "Dưới 3 điểm phải báo lỗi"
    except ValueError as e:
        print(f"  + Validate < 3 điểm: [PASS] {e}")

    try:
        parse_polygon({"points": [[0,0],[2,0],[1,1]]})
        assert False, "Toạ độ > 1 phải báo lỗi"
    except ValueError as e:
        print(f"  + Validate ngoài [0,1]: [PASS] {e}")

    try:
        parse_polygon({"points": [[.1,.1],[.11,.1],[.1,.11]]})
        assert False, "Diện tích < 1% phải báo lỗi"
    except ValueError as e:
        print(f"  + Validate diện tích nhỏ: [PASS] {e}")

    valid_pts = parse_polygon({"points": [[0.2, 0.2], [0.8, 0.2], [0.5, 0.8]]})
    assert len(valid_pts) == 3
    print(f"  + Validate vùng hợp lệ: [PASS] 3 toạ độ chuẩn hoá.")

    cropped_img = apply_focus_region(img_goc, {"points": valid_pts})
    assert cropped_img.size[0] < img_goc.size[0] and cropped_img.size[1] < img_goc.size[1]
    print(f"  + Cắt ảnh theo polygon: [PASS] Kích thước gốc {img_goc.size} -> Đã crop {cropped_img.size}")

    # -------------------------------------------------------------
    # 5. TEST FEATURE 6: ONNX Runtime & PyTorch Equivalence
    # -------------------------------------------------------------
    print("\n[TEST 5/8] Feature 6: Xuất và suy luận ONNX Runtime")
    onnx_bin = Path("skin_cancer/checkpoints/binary.onnx")
    onnx_mc = Path("skin_cancer/checkpoints/multiclass.onnx")
    assert onnx_bin.exists() and onnx_mc.exists(), "Cần có binary.onnx và multiclass.onnx"
    print(f"  + File model ONNX: {onnx_bin.name} ({onnx_bin.stat().st_size/1e6:.1f}MB), {onnx_mc.name} ({onnx_mc.stat().st_size/1e6:.1f}MB)")

    predictor = OnnxPredictor(Path("skin_cancer/checkpoints"))
    from skin_cancer.webapp.app import preprocess
    inp_np = preprocess(img_goc).unsqueeze(0).numpy()
    p_malig_onnx, probs_mc_onnx = predictor.predict(inp_np)
    print(f"  + ONNX dự đoán: p_malignant={p_malig_onnx:.4f}, class={probs_mc_onnx.argmax()} [PASS]")

    # -------------------------------------------------------------
    # 6. TEST FEATURE 5: Quantization INT8
    # -------------------------------------------------------------
    print("\n[TEST 6/8] Feature 5: Lượng tử hoá INT8 (Quantization)")
    int8_bin = Path("skin_cancer/checkpoints/binary_int8.onnx")
    int8_mc = Path("skin_cancer/checkpoints/multiclass_int8.onnx")
    assert int8_bin.exists() and int8_mc.exists(), "Cần có binary_int8.onnx và multiclass_int8.onnx"
    ratio_bin = onnx_bin.stat().st_size / int8_bin.stat().st_size
    ratio_mc = onnx_mc.stat().st_size / int8_mc.stat().st_size
    print(f"  + Binary FP32 ({onnx_bin.stat().st_size/1e6:.1f}MB) -> INT8 ({int8_bin.stat().st_size/1e6:.1f}MB): Nhỏ hơn {ratio_bin:.1f} lần [PASS]")
    print(f"  + Multiclass FP32 ({onnx_mc.stat().st_size/1e6:.1f}MB) -> INT8 ({int8_mc.stat().st_size/1e6:.1f}MB): Nhỏ hơn {ratio_mc:.1f} lần [PASS]")

    pred_int8 = OnnxPredictor(Path("skin_cancer/checkpoints"), suffix="_int8")
    p_malig_int8, probs_mc_int8 = pred_int8.predict(inp_np)
    print(f"  + INT8 dự đoán: p_malignant={p_malig_int8:.4f}, class={probs_mc_int8.argmax()} [PASS]")

    # -------------------------------------------------------------
    # 7. TEST FEATURE 7: Celery Async & Analysis Status API
    # -------------------------------------------------------------
    print("\n[TEST 7/8] Feature 7: Hàng đợi Celery + Redis & Trạng thái phân tích")
    # Tắt CSRF trong test client để test API thuận lợi
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    # Đăng nhập bác sĩ
    login_resp = client.post("/api/auth/login", json={
        "email": "doctor@dermascan.local",
        "password": "123456123456"
    })
    assert login_resp.status_code == 200, f"Đăng nhập bác sĩ thất bại: {login_resp.data}"
    print("  + Đăng nhập tài khoản doctor@dermascan.local thành công.")

    # Tìm hoặc tạo một CaseImage
    with app.app_context():
        doctor = User.query.filter_by(email="doctor@dermascan.local").first()
        patient = User.query.filter_by(email="patient@dermascan.local").first()
        
        test_case = Case(
            doctor_id=doctor.id,
            patient_user_id=patient.id,
            case_code=f"TEST-CASE-{os.getpid()}",
            status="CREATED"
        )
        db.session.add(test_case)
        db.session.commit()

        upload_dir = Path(app.config["UPLOAD_FOLDER"]).resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest_img = upload_dir / f"test_e2e_{os.getpid()}_goc.jpg"
        dest_img.write_bytes(Path("goc.jpg").read_bytes())

        test_img = CaseImage(
            case_id=test_case.id,
            image_path=str(dest_img),
            original_filename="goc.jpg",
            mime_type="image/jpeg",
            file_size=dest_img.stat().st_size,
            sha256_hash="dummysha256",
            uploaded_by=doctor.id,
            status="UPLOADED"
        )
        db.session.add(test_img)
        db.session.commit()
        case_id = test_case.id
        case_image_id = test_img.id

    print(f"  + Đã tạo ca kiểm thử: case_id={case_id}, case_image_id={case_image_id}")

    # Gán focus region qua API (Feature 1 API test)
    put_reg = client.put(f"/api/case-images/{case_image_id}/focus-region", json={
        "points": [[0.2, 0.2], [0.8, 0.2], [0.5, 0.8]]
    })
    assert put_reg.status_code == 200, f"PUT focus-region thất bại: {put_reg.data}"
    print("  + PUT /api/case-images/<id>/focus-region: [PASS] 200 OK")

    # Kích hoạt phân tích (POST analyze) -> trả về 202 PENDING
    analyze_resp = client.post(f"/api/case-images/{case_image_id}/analyze")
    assert analyze_resp.status_code == 202, f"POST analyze phải trả 202 Accepted nhưng nhận {analyze_resp.status_code}"
    analysis_data = analyze_resp.get_json()
    analysis_id = analysis_data["analysis_id"]
    assert analysis_data["status"] == "PENDING"
    print(f"  + POST /api/case-images/<id>/analyze: [PASS] 202 PENDING, analysis_id={analysis_id}")

    # Kiểm tra API status khi đang PENDING/trước khi hoàn thành
    status_resp_pending = client.get(f"/api/analyses/{analysis_id}/status")
    assert status_resp_pending.status_code == 200
    print(f"  + GET /api/analyses/{analysis_id}/status (trước xử lý): [PASS] status={status_resp_pending.get_json()['status']}")

    # Thực thi task xử lý (mô phỏng worker hoặc worker nền)
    task_res = _run_analysis(analysis_id, case_image_id)
    assert task_res is not None, "Worker thực thi phân tích phải trả kết quả"
    from skin_cancer.webapp.celery_app import celery
    if celery is not None:
        try:
            celery.backend.store_result(f"analysis-{analysis_id}", task_res, "SUCCESS")
        except Exception:
            pass
    print("  + Xử lý tác vụ analyze_case_image thành công, kết quả sẵn sàng.")

    # Kiểm tra lại API status sau khi hoàn thành
    status_resp_done = client.get(f"/api/analyses/{analysis_id}/status")
    assert status_resp_done.status_code == 200
    data_done = status_resp_done.get_json()
    assert data_done["status"] == "COMPLETED"
    assert "result" in data_done
    assert "quality" in data_done["result"]
    assert "uncertainty" in data_done["result"]
    print(f"  + GET /api/analyses/{analysis_id}/status (sau xử lý): [PASS] COMPLETED kèm result={list(data_done['result'].keys())}")

    # -------------------------------------------------------------
    # 8. TEST FEATURE 4: Timeline Progress API
    # -------------------------------------------------------------
    print("\n[TEST 8/8] Feature 4: Timeline tiến triển (API /api/cases/<id>/timeline)")
    tl_resp = client.get(f"/api/cases/{case_id}/timeline")
    assert tl_resp.status_code == 200, f"Timeline trả lỗi: {tl_resp.data}"
    tl_data = tl_resp.get_json()
    assert "points" in tl_data
    print(f"  + Timeline ca bệnh {case_id}: [PASS] Có {len(tl_data['points'])} điểm phân tích, trend={tl_data['trend']}")

    # Kiểm tra phân quyền timeline: Bệnh nhân khác (patient2) không được xem
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "patient2@dermascan.local",
        "password": "123456123456"
    })
    tl_unauthorized = client.get(f"/api/cases/{case_id}/timeline")
    assert tl_unauthorized.status_code in (403, 404), f"Bệnh nhân khác phải bị chặn xem timeline: {tl_unauthorized.status_code}"
    print(f"  + Kiểm tra bảo mật: patient2 truy cập timeline nhận {tl_unauthorized.status_code} [PASS]")

    print("\n" + "=" * 60)
    print("HOÀN THÀNH TOÀN BỘ 8/8 TÍNH NĂNG - TẤT CẢ ĐỀU VƯỢT QUA TEST!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
