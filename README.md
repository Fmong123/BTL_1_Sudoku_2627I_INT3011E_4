# Chạy chương trình Sudoku

Chương trình sinh đề Sudoku và so sánh các bộ giải SAT, CP và MIP. Thực hiện các bước dưới đây trong Terminal PowerShell của VS Code, tại thư mục gốc dự án.

## 1. Cài đặt thư viện

Cài Python, sau đó tạo môi trường và cài các thư viện:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Nếu đã có môi trường `.venv` thì bỏ qua lệnh tạo môi trường. Các lệnh bên dưới dùng trực tiếp Python trong `.venv`, không cần kích hoạt môi trường.

## 2. Chuẩn bị dữ liệu

Nếu chưa có dữ liệu, mở `generate.py` và sửa các cấu hình ở đầu file. Ví dụ sinh 10 đề Sudoku 9×9:

```python
GENERATION_MODE = "sat_only"
OUTPUT_DIR = None
SIZES = [9]
SEED = 42
OVERWRITE = False
COUNT_PER_SIZE = 10
CLUE_RATIOS = [0.4]
```

Chạy:

```powershell
.\.venv\Scripts\python.exe generate.py
```

Dữ liệu được tạo tại `data/sat_only/9x9/generated.csv`, kèm manifest `data/sat_only/dataset.json`. Với ví dụ này, không cần chỉnh `COUNTS` vì cấu hình đó chỉ dùng cho chế độ `mixed`.

Nếu đã có đúng bộ dữ liệu cần chạy thì bỏ qua bước sinh. `OVERWRITE = False` ngăn ghi đè bộ dữ liệu đã có; chỉ đổi thành `True` khi muốn thay dữ liệu cũ.

## 3. Cấu hình và chạy file chính

Mở `main.py`, sửa các cấu hình ở đầu file. Ví dụ chạy toàn bộ 10 đề vừa sinh với SAT và CP-SAT:

```python
DATASET = "sat_only"
SIZES = [9]
INPUT_DIR = None
RESULT_DIR = None
INPUT_FILE = None
PUZZLE_NUMBERS = None
METHODS = ["sat", "cp-sat"]
SAT_SOLVER = "glucose3"
ENCODINGS = ["pairwise", "seqcounter", "bitwise", "commander", "product"]
TIME_LIMIT = 30
REPEATS = 1
SEED = 42
```

- `DATASET` chọn bộ dữ liệu `sat_only` hoặc `mixed`; phải khớp với dữ liệu đã sinh.
- `SIZES` chọn kích thước cần chạy, ví dụ `[9]`, `[16]`, `[25]` hoặc `[9, 16, 25]`. Cần có dữ liệu cho từng kích thước đã chọn.
- `PUZZLE_NUMBERS = None` chạy tất cả các đề. Dùng `list(range(1, 11))` để chạy 10 đề đầu của mỗi kích thước nếu bộ dữ liệu có đủ.
- `ENCODINGS` chọn các cách mã hóa cho phương pháp SAT.
- `TIME_LIMIT` là ngân sách tính bằng giây cho build + solve mỗi lượt; bước build không bị ngắt giữa chừng nên thời gian thực tế có thể vượt ngân sách.
- `REPEATS` là số lần chạy mỗi cấu hình trên mỗi đề.

Chạy file chính:

```powershell
.\.venv\Scripts\python.exe main.py
```

Cấu hình trong `generate.py` chỉ dùng để sinh dữ liệu. Khi chạy, `main.py` đọc bộ dữ liệu theo cấu hình riêng của nó.

Có thể thêm `"cplex-mip"`, `"gurobi-mip"` hoặc `"cplex-cp"` vào `METHODS` khi đã cài solver và có license phù hợp. Riêng `cplex-cp` cần CP Optimizer: đặt biến môi trường `CP_OPTIMIZER_EXECUTABLE` trỏ đến executable và cấu hình PATH cho các DLL cần thiết trên Windows. Cài thư viện Python không tự cung cấp đầy đủ engine và license cho mọi phương pháp.

## 4. Xem kết quả

Với `DATASET = "sat_only"` và `RESULT_DIR = None`, chương trình lưu:

```text
results/sat_only/
  ket_qua.csv          # Kết quả chi tiết của các lượt chạy
  tong_hop.csv         # Bảng tổng hợp
  9x9/
    ket_qua.csv
    tong_hop.csv
```

Các kích thước khác có thư mục tương ứng. Chọn `DATASET = "mixed"` thì kết quả mặc định nằm trong `results/mixed/`.

`main.py` tự lưu và cập nhật tổng hợp khi hoàn thành đợt chạy. Những lần chạy sau được nối vào kết quả cũ. Nhấn `Ctrl+C` để dừng; đợt đang chạy dở không được lưu.
