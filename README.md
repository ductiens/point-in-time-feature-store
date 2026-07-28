python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
deactivate

flowchart TD
A["Dữ liệu giao dịch"]
B["Tạo UID và Warehouse"]
C["Định nghĩa Feature"]

    D["Offline<br/>Tính feature để train model và backfill"]
    E["Online<br/>Lưu lịch sử trong Redis và trả feature qua API"]

    F["Parity Test<br/>Kiểm tra Offline và Online có giống nhau không"]

    A --> B
    B --> C

    C --> D
    C --> E

    D --> F
    E --> F

card1 + addr1 → đơn giản hơn, có nguy cơ rộng hơn về mặt logic
card1 + card2 + addr1 → chi tiết hơn nhưng gần như giữ nguyên chất lượng thống kê
thêm card5 → phức tạp hơn nhưng cải thiện rất ít. Không cần thêm card5, vì thêm vào nhưng kết quả gần như không cải thiện đáng kể.
thêm D1 → quá hẹp, chia vụn entity. vì tạo tới 231.565 entity, median 1, repeat entity chỉ 26,04% → D1 làm cùng một người bị tách thành nhiều UID.

| Nhóm cần kiểm tra                | Cột dùng để nhìn                                           | Câu hỏi                                                     |
| -------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------- |
| **Độ phủ**                       | `total_rows`, `rows_with_uid`, `coverage_pct`              | Công thức tạo UID dùng được cho bao nhiêu giao dịch?        |
| **Mức độ chia nhỏ**              | `n_entities`, `repeat_entity_pct`, `median_txn_per_entity` | Có phải mỗi giao dịch gần như thành một entity riêng không? |
| **Khả năng tạo feature lịch sử** | `repeat_row_pct`                                           | Bao nhiêu giao dịch thực sự nằm trong entity có lịch sử?    |
| **Nguy cơ gom quá rộng**         | `p95_txn_per_entity`, `max_txn_per_entity`                 | Có entity nào chứa quá nhiều giao dịch bất thường không?    |



python -c "import duckdb; con=duckdb.connect('warehouse.duckdb'); print(con.sql('SELECT * FROM transactions LIMIT 20').df())"   