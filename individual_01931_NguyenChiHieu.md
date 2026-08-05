# Báo cáo cá nhân — Day 9 Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Nguyễn Chí Hiếu |
| MSSV | 2A202601931 |
| Khóa/Lớp | K3 |
| Vai trò chính | Cá nhân — thiết kế, triển khai và kiểm thử toàn bộ pipeline |
| Ngày hoàn thành | 2026-08-05 |

## 2. Phạm vi công việc

| Module/deliverable | File phụ trách | Input | Output | Trạng thái |
|---|---|---|---|---|
| Data indexing và context | `app/data_repository.py` | Olist CSV, order IDs | `CaseContext` bất biến | Hoàn thành |
| Multi-agent handoff | `app/agents.py`, `app/pipeline.py` | Typed facts | Decision và output draft | Hoàn thành |
| Policy và financial logic | `app/policy.py` | `CaseContext` | Rule đầu tiên khớp | Hoàn thành |
| Groq audit | `app/llm_audit.py` | Handoff selection | Audit JSON | Hoàn thành |
| Validation và packaging | `scripts/validate_and_package.py` | 50 outputs | `output.zip` | Hoàn thành |
| Architecture, trace, metadata | `architecture.md`, `logging/` | Lượt chạy thật | Tài liệu và audit artifact | Hoàn thành |

## 3. Kết quả

- Xử lý đủ 50 input mà không hard-code case ID hoặc order ID.
- Sinh đủ 50 JSON và archive chỉ chứa đúng 50 file.
- Phân bố issue: 8 canceled, 8 unavailable, 8 seller late, 8 logistics late, 9 split payment hợp lệ và 9 late claim không được hỗ trợ.
- Groq audit: 50 request thành công, 50 quyết định handoff được đồng thuận.
- Automated tests: 4/4 pass.
- Secret scan: không phát hiện API key trong source/artifact.

Artifact chính: `output/`, `output.zip`, `logging/trace.jsonl`, `logging/metadata.json`.

## 4. Giải thích kỹ thuật

Pipeline không dùng nội dung khiếu nại làm ground truth. `claimed_order_id` được dùng để tạo context từ orders, items, payments và sellers. Ba specialist agent chỉ trả fact packet thuộc domain của mình. Policy Agent nhận `InvestigationBundle`, duyệt sáu rule theo thứ tự `EC_POLICY_V1`, rồi tạo draft. Verifier Agent đánh giá policy lần nữa, tính lại tiền bằng `Decimal`, kiểm tra evidence tồn tại trong CSV và chỉ cho phép ghi file khi không có lỗi.

Các contract đầu vào, handoff và đầu ra đều dùng Pydantic với `extra="forbid"`. File output được ghi qua file tạm và replace để tránh JSON dở dang. Mỗi run truncate trace cũ trước khi ghi, đúng yêu cầu chỉ giữ lượt mới nhất.

### Cách xác minh

```powershell
python -m pytest
python -m app.main --llm-audit
python -m scripts.validate_and_package
```

Kết quả thực tế: 4 test pass; 50 output được verifier chấp nhận; 50/50 model audit thành công và đồng thuận; `output.zip` có đúng 50 JSON.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** LLM 8B nhanh nhưng có thể diễn giải sai policy hoặc tạo ID/số tiền không tồn tại.
- **Phương án cân nhắc:** để LLM quyết định toàn bộ; hoặc dùng rule engine authoritative và LLM làm audit handoff.
- **Phương án chọn:** kiến trúc hybrid, deterministic data/policy/verifier và non-authoritative Groq audit.
- **Lý do:** tối đa correctness, reproducibility và khả năng mở rộng; API failure không làm hỏng output.
- **Bằng chứng:** verifier chấp nhận 50/50 output; audit cuối đồng thuận 50/50; không có case ID trong source.

## 6. Lỗi/blocker đã xử lý

- **Triệu chứng:** request Groq đầu tiên trả `NotFoundError`.
- **Nguyên nhân:** `.env` dùng OpenAI-compatible URL kết thúc bằng `/openai/v1`, trong khi Groq SDK tự thêm route đó.
- **Xử lý:** chuẩn hóa base URL trước khi tạo Groq client.
- **Xác minh:** 50/50 request audit cuối thành công.

Một lỗi chất lượng khác là model ban đầu tự thêm điều kiện không có trong policy khi audit giao trễ. Cách xử lý là không giao quyền policy cho model; audit chỉ so sánh rule đầu tiên đã match với quyết định handoff, còn Verifier Agent kiểm tra nghiệp vụ độc lập.

## 7. Hiểu biết end-to-end và hidden challenges

1. Input được validate, sau đó order ID được join vào snapshot Olist đã index một lần.
2. Các agent trao đổi fact packet có schema thay vì truyền prompt chứa toàn bộ CSV.
3. Policy priority xử lý overlap giữa split payment và delivery-within-estimate.
4. Unavailable order có thể không có item; khi đó item/seller rỗng nhưng full payment vẫn được refund.
5. Nhiều item/payment phải được cộng bằng `Decimal`; evidence dùng row identifier thật và tuân thủ giới hạn số lượng.
6. Verifier độc lập là quality gate cuối; LLM output không thể trực tiếp đi vào file nộp.

## 8. Cam kết

- [x] Báo cáo phản ánh đúng phần việc đã thực hiện.
- [x] Có thể giải thích luồng end-to-end và contract giữa các agent.
- [x] Chỉ ghi thành công cho các lệnh/artifact đã xác minh.
- [x] Báo cáo và source không chứa API key, token hoặc secret.
- [x] Nội dung là báo cáo cá nhân, không sao chép báo cáo thành viên khác.

**Họ và tên:** Nguyễn Chí Hiếu  
**Ngày xác nhận:** 2026-08-05

