name: finance-advisory
description: Sử dụng khi người dùng hỏi về tư vấn ngân sách thuê nhà, khả năng chi trả dựa trên mức thu nhập hoặc lương hàng tháng.

# Workflow
1. Nếu người dùng đề cập đến mức lương hoặc thu nhập, dùng LLM trích xuất số tiền và tự động chuyển đổi sang số nguyên (đơn vị VND).
2. Gọi công cụ `calculate_affordability` từ file `app/agent.py` để tính toán khoảng ngân sách thuê trọ tối ưu (chiếm từ 25% đến 35% tổng thu nhập).
3. Định dạng và chuyển đổi kết quả tư vấn sang cấu trúc JSON card `A2UI_BudgetAdvice` để hiển thị trực quan lên giao diện chat.
4. Chủ động sử dụng mức ngân sách tối đa vừa tính toán để liên kết, chuyển tiếp tự động sang bước gọi công cụ `query_database`, giúp tìm kiếm và hiển thị ngay danh sách phòng trọ hoặc nhà nguyên căn phù hợp với túi tiền của người dùng.
