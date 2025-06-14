import csv
import time
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# uint_to_float 函数
def uint_to_float(x_int, x_min, x_max, bits):
    span = x_max - x_min
    offset = x_min
    return (float(x_int) * span / float((1 << bits) - 1)) + offset

# 解析CAN数据帧的位置值
def parse_position(data):
    if len(data) != 8 or data[0] != 0x01:  # 仅处理电机返回数据 (Data[0] == 0x01)
        return None
    # 位置值：Data[1] (高8位) + Data[2] (低8位)
    pos_int = (data[1] << 8) | data[2]
    # 转换为浮点数，16位，范围 [-π, π]
    pos_rad = uint_to_float(pos_int, -3.14159, 3.14159, 16)
    return pos_rad

# 尝试以不同编码读取文件
def read_csv_with_encoding(file_path):
    encodings = ['gbk', 'utf-8', 'latin1']  # 优先尝试GBK
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                reader = csv.reader(f)
                return list(reader), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"无法以任何编码读取文件: {file_path}", b"", 0, 0, "尝试了所有编码")

# CSV文件监控器
class CSVHandler(FileSystemEventHandler):
    def __init__(self, data_dict, times, max_points=100):
        self.data_dict = data_dict  # 存储 {id: [positions]}
        self.times = times  # 存储时间戳
        self.max_points = max_points  # 最大显示点数
        self.last_processed = 0  # 最后处理的行数

    def on_modified(self, event):
        if event.src_path.endswith('data_0004.csv'):
            try:
                rows, encoding = read_csv_with_encoding('data_0004.csv')
                # 从上次处理的位置开始
                for row in rows[self.last_processed:]:
                    try:
                        # 确保行有足够列
                        if len(row) < 10:
                            print(f"行数据不足: {row}")
                            continue
                        # 解析数据列
                        data_str = row[9] if len(row) > 9 else row[8]  # 兼容9或10列
                        if '|' not in data_str:
                            print(f"数据格式错误: {data_str}")
                            continue
                        data_hex = data_str.split('|')[1].strip().split()
                        if len(data_hex) != 8:
                            print(f"数据字节数错误: {data_hex}")
                            continue
                        data = [int(x, 16) for x in data_hex]
                        can_id = int(row[5], 16)  # ID号
                        pos = parse_position(data)
                        if pos is not None:
                            # 添加数据到对应ID
                            if can_id not in self.data_dict:
                                self.data_dict[can_id] = []
                            self.data_dict[can_id].append(pos)
                            self.times.append(int(row[2], 16))  # 时间标识，转换为十进制
                            # 限制数据点数
                            if len(self.data_dict[can_id]) > self.max_points:
                                self.data_dict[can_id].pop(0)
                                self.times.pop(0)
                    except (IndexError, ValueError) as e:
                        print(f"解析错误: {e}, 行: {row}")
                self.last_processed = len(rows)
            except Exception as e:
                print(f"文件读取错误: {e}")

# 实时绘图
def animate(i, data_dict, times, ax, lines):
    # 更新现有折线而不是清除整个图
    if not lines:  # 初始化折线
        for can_id in data_dict:
            line, = ax.plot([], [], label=f'ID {hex(can_id)}', linewidth=2)
            lines[can_id] = line
    for can_id, positions in data_dict.items():
        if positions:  # 更新折线数据
            line = lines.get(can_id)
            if line:
                line.set_data(times[-len(positions):], positions)
    # 调整视图
    ax.relim()
    ax.autoscale_view()
    ax.set_xlabel('时间标识 (十进制)')
    ax.set_ylabel('位置 (弧度)')
    ax.set_title('电机位置实时图')
    ax.legend()
    ax.grid(True)
    return list(lines.values())

# 主函数
def main():
    # 初始化数据存储
    data_dict = {}  # {can_id: [positions]}
    times = []  # 时间戳
    max_points = 100  # 最大显示点数

    # 设置Matplotlib
    fig, ax = plt.subplots()
    lines = {}  # 存储 {can_id: line}，避免重复创建折线
    ani = FuncAnimation(fig, animate, fargs=(data_dict, times, ax, lines), interval=50, blit=True)

    # 设置文件监控
    event_handler = CSVHandler(data_dict, times, max_points)
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()

    try:
        plt.show()  # 显示实时图
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == '__main__':
    main()