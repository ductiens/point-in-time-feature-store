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

card1 + addr1 → Đơn giản nhất nhưng dễ bị trùng nhầm (2 cột quá thô, addr1 dùng chung cho nhiều người)
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



flowchart TD
    S0["Sprint 0 — Bootstrap<br/>Khởi tạo repo, .gitignore<br/>và thư mục kết quả"]

    S1["Sprint 1 — Setup & Data<br/>Chuẩn bị dữ liệu IEEE-CIS<br/>Chọn công thức pseudo-entity<br/>Khởi tạo DuckDB warehouse"]

    S2["Sprint 2 — Feature Catalog<br/>Định nghĩa 4 feature<br/>Đọc, validate và test catalog"]

    S3["Sprint 3 — Offline Engine<br/>Tính feature Point-in-Time<br/>Không dùng giao dịch hiện tại<br/>hoặc dữ liệu tương lai"]

    S4["Sprint 4 — Leakage Experiment<br/>So sánh PIT-correct và leaky<br/>ROC-AUC và PR-AUC"]

    S5["Sprint 5 — Backfill<br/>Tính lại feature lịch sử<br/>Tái lập, lưu Parquet<br/>và quản lý phiên bản"]

    S6["Sprint 6 — Online Feature Store<br/>Redis + FastAPI + Replay dữ liệu<br/><b>PHẦN MỞ RỘNG</b><br/>Thực hiện nếu còn thời gian"]

    S7["Sprint 7 — Offline/Online Parity<br/>So sánh DuckDB và Redis<br/>0 sai lệch trên ít nhất 50 mẫu<br/><b>PHẦN MỞ RỘNG</b>"]

    S8["Sprint 8 — Monitoring<br/>Freshness và Distribution Drift<br/><b>PHẦN MỞ RỘNG</b>"]

    S9["Sprint 9 — Docs & Report<br/>Proposal, kiến trúc<br/>và báo cáo kết quả thực tế"]


    S0 -->|"Repo sẵn sàng"| S1
    S1 -->|"Warehouse và entity sẵn sàng"| S2
    S2 -->|"Catalog hợp lệ"| S3
    S3 -->|"Offline feature hoàn thành"| S4
    S3 -->|"Offline feature hoàn thành"| S5

    S4 -->|"Có kết quả leakage experiment"| S9
    S5 -->|"Có kết quả backfill"| S9

    S2 -.->|"Nếu còn thời gian"| S6

    S3 -.->|"Có Offline Engine"| S7
    S6 -.->|"Có Online Engine"| S7

    S7 -.->|"Nếu còn thời gian"| S8

    S7 -.->|"Ghi kết quả parity nếu đã triển khai"| S9
    S8 -.->|"Ghi kết quả monitoring nếu đã triển khai"| S9

    classDef optional fill:#f5f5f5,stroke:#757575,stroke-width:2px,stroke-dasharray:6 4;

    class S0,S1 setup;
    class S2,S3,S5 core;
    class S4 experiment;
    class S6,SK,S7,S8 optional;
    class S9,S10 final;