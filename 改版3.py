import os
import sqlite3
import numpy as np
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional
import tkinter as tk
from tkinter import messagebox, ttk


class SmartShelfOptimizer:
    def __init__(
            self,
            camera_height: float = 1.8,  # 摄像头安装高度(米)
            camera_angle: float = 0,  # 摄像头俯角(度)
            reference_height: float = 1.75,  # 参考身高(米)
            shelf_layout: Dict[str, Tuple[float, float]] = None,  # 货架布局 {区域名称: (起始高度, 结束高度)}
            history_frames: int = 30,  # 历史数据保留帧数
            gaze_weight: float = 0.6,  # 视线权重(0-1)
            sales_weight: float = 0.3,  # 销售权重(0-1)
            interaction_weight: float = 0.1,  # 互动权重(0-1)
            db_file: str = "smart_shelf.db3"  # 数据库文件路径
    ):
        # 初始化参数
        self.camera_height = camera_height
        self.camera_angle = np.radians(camera_angle)
        self.reference_height = reference_height
        self.history_frames = history_frames
        self.gaze_weight = gaze_weight
        self.sales_weight = sales_weight
        self.interaction_weight = interaction_weight
        self.db_file = db_file

        # 货架布局(默认四层货架)
        self.shelf_layout = shelf_layout or {
            "top": (1.6, 1.8),  # 顶层货架
            "upper_middle": (1.4, 1.6),  # 中上层货架
            "lower_middle": (1.2, 1.4),  # 中下层货架
            "bottom": (0.8, 1.2)  # 底层货架
        }

        # 初始化数据存储
        self.height_history = deque(maxlen=history_frames)  # 身高历史数据
        self.item_data = defaultdict(lambda: {
            "sales": 0,  # 销售量
            "pickups": 0,  # 拿起次数
            "dropoffs": 0,  # 放下次数
            "current_stock": 0,  # 当前库存
            "position": None  # 当前位置
        })
        self.gaze_data = defaultdict(int)  # 视线停留区域统计

        # 连接数据库
        self.conn = sqlite3.connect(self.db_file)
        self.cursor = self.conn.cursor()

        # 检查数据库是否存在且有数据
        self.db_exists = os.path.exists(self.db_file) and self._check_tables_exist()

        if self.db_exists:
            print(f"使用现有数据库文件: {self.db_file}")
            self.load_data_from_db()
        else:
            print(f"创建新数据库文件: {self.db_file}")
            self.create_tables()

    def _check_tables_exist(self) -> bool:
        """检查数据库中是否存在所有必需的表"""
        try:
            # 查询所有已存在的表
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = set(row[0] for row in self.cursor.fetchall())
            # 必需的表集合
            required_tables = {"item_data", "gaze_data", "height_history"}
            # 检查所有必需表是否存在
            return required_tables.issubset(existing_tables)
        except Exception as e:
            print(f"检查数据库表存在性时出错: {e}")
            return False

    def create_tables(self) -> None:
        """创建数据库表（新增身高历史表）"""
        # 商品表（原逻辑保留）
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS item_data (
                item_id TEXT PRIMARY KEY,
                sales INTEGER,
                pickups INTEGER,
                dropoffs INTEGER,
                current_stock INTEGER,
                position TEXT
            )
        ''')
        # 视线数据表（原逻辑保留）
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS gaze_data (
                zone TEXT PRIMARY KEY,
                count INTEGER
            )
        ''')
        # 新增：身高历史表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS height_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                height REAL
            )
        ''')
        self.conn.commit()

    def load_data_from_db(self) -> None:
        """从数据库加载数据（新增身高数据加载）"""
        # 加载商品数据（原逻辑保留）
        self.cursor.execute('SELECT item_id, sales, pickups, dropoffs, current_stock, position FROM item_data')
        for item_id, sales, pickups, dropoffs, current_stock, position in self.cursor.fetchall():
            self.item_data[item_id] = {
                "sales": sales,
                "pickups": pickups,
                "dropoffs": dropoffs,
                "current_stock": current_stock,
                "position": position
            }
        # 加载视线数据（原逻辑保留）
        self.cursor.execute('SELECT zone, count FROM gaze_data')
        for zone, count in self.cursor.fetchall():
            self.gaze_data[zone] = count
        # 新增：加载身高数据
        self.cursor.execute('SELECT height FROM height_history')
        for row in self.cursor.fetchall():
            self.height_history.append(row[0])

    def calibrate_height(self, pixel_height: float) -> float:
        """根据像素高度和参考身高校准实际身高"""
        if pixel_height <= 0:
            return 0
        return (self.reference_height * 240) / pixel_height  # 假设参考身高对应240像素

    def update_height_data(self, pixel_height: float) -> None:
        """更新身高数据（新增数据库写入逻辑）"""
        actual_height = self.calibrate_height(pixel_height)
        if 1.0 <= actual_height <= 2.2:  # 过滤异常值
            self.height_history.append(actual_height)
            # 无论数据库是否存在都写入数据
            self.cursor.execute('INSERT INTO height_history (height) VALUES (?)', (actual_height,))
            self.conn.commit()

    def calculate_gaze_range(self, height: Optional[float] = None) -> Tuple[float, float]:
        """计算舒适视线范围(基于人体工程学)"""
        if height is None:
            if not self.height_history:
                return (1.4, 1.7)  # 默认视线范围
            height = np.mean(self.height_history)

        # 视线高度 = 身高 * 0.95 (站立时眼睛高度约为身高的95%)
        eye_level = height * 0.95

        # 舒适视线范围 = 视线高度 ± 0.15米
        lower_bound = max(0.5, eye_level - 0.10)  # 确保不低于地面
        upper_bound = min(1.8, eye_level + 0.10)  # 确保不高于天花板

        return (lower_bound, upper_bound)

    def update_item_status(self, item_id: str, stock: int, position: str) -> None:
        """更新商品状态"""
        self.item_data[item_id]["current_stock"] = stock
        self.item_data[item_id]["position"] = position

        # 无论数据库是否存在都更新数据
        self.cursor.execute('''
            INSERT OR REPLACE INTO item_data (item_id, sales, pickups, dropoffs, current_stock, position)
            VALUES (?,?,?,?,?,?)
        ''', (item_id, self.item_data[item_id]["sales"], self.item_data[item_id]["pickups"],
              self.item_data[item_id]["dropoffs"], stock, position))
        self.conn.commit()

    def record_interaction(self, item_id: str, interaction_type: str) -> None:
        """记录商品互动(拿起/放下)"""
        if interaction_type == "pickup":
            self.item_data[item_id]["pickups"] += 1
        elif interaction_type == "dropoff":
            self.item_data[item_id]["dropoffs"] += 1

        # 无论数据库是否存在都更新数据
        self.cursor.execute('''
            UPDATE item_data
            SET pickups = ?, dropoffs = ?
            WHERE item_id = ?
        ''', (self.item_data[item_id]["pickups"], self.item_data[item_id]["dropoffs"], item_id))
        self.conn.commit()

    def record_sale(self, item_id: str, quantity: int = 1) -> None:
        """记录商品销售"""
        self.item_data[item_id]["sales"] += quantity
        self.item_data[item_id]["current_stock"] -= quantity

        # 无论数据库是否存在都更新数据
        self.cursor.execute('''
            UPDATE item_data
            SET sales = ?, current_stock = ?
            WHERE item_id = ?
        ''', (self.item_data[item_id]["sales"], self.item_data[item_id]["current_stock"], item_id))
        self.conn.commit()

    def restock_item(self, item_id: str, quantity: int = 1) -> None:
        """记录商品补货"""
        self.item_data[item_id]["current_stock"] += quantity

        # 无论数据库是否存在都更新数据
        self.cursor.execute('''
            UPDATE item_data
            SET current_stock = ?
            WHERE item_id = ?
        ''', (self.item_data[item_id]["current_stock"], item_id))
        self.conn.commit()

    def update_gaze_data(self, y_position: float) -> None:
        """更新视线停留区域数据"""
        for zone, (start, end) in self.shelf_layout.items():
            if start <= y_position <= end:
                self.gaze_data[zone] += 1

                # 无论数据库是否存在都更新数据
                self.cursor.execute('''
                    INSERT OR REPLACE INTO gaze_data (zone, count)
                    VALUES (?,?)
                ''', (zone, self.gaze_data[zone]))
                self.conn.commit()
                break

    def calculate_shelf_scores(self) -> Dict[str, float]:
        """计算各货架区域的吸引力分数"""
        # 1. 基于视线停留频率计算得分
        total_gaze = sum(self.gaze_data.values())
        gaze_scores = {
            zone: (self.gaze_data.get(zone, 0) / total_gaze)
            for zone in self.shelf_layout
        } if total_gaze > 0 else {zone: 1 / len(self.shelf_layout) for zone in self.shelf_layout}

        # 2. 基于人体工程学计算得分
        ideal_lower, ideal_upper = self.calculate_gaze_range()
        ergonomic_scores = {}
        for zone, (start, end) in self.shelf_layout.items():
            # 计算区域与理想视线范围的重叠比例
            overlap_start = max(start, ideal_lower)
            overlap_end = min(end, ideal_upper)
            overlap = max(0, overlap_end - overlap_start)
            zone_height = end - start
            ergonomic_scores[zone] = overlap / zone_height if zone_height > 0 else 0

        # 3. 综合得分(视线权重 * 视线得分 + (1-视线权重) * 人体工程学得)
        combined_scores = {
            zone: self.gaze_weight * gaze_scores[zone] + (1 - self.gaze_weight) * ergonomic_scores[zone]
            for zone in self.shelf_layout
        }

        return combined_scores

    def recommend_item_positions(self, priority_items: List[str] = None) -> Dict[str, str]:
        """推荐商品摆放位置"""
        # 1. 计算货架区域得分
        shelf_scores = self.calculate_shelf_scores()
        sorted_zones = sorted(shelf_scores.items(), key=lambda x: x[1], reverse=True)

        # 2. 计算商品优先级得分
        item_priorities = {}
        for item_id, data in self.item_data.items():
            # 综合考虑销售量、互动率和是否为优先商品
            priority = (
                    self.sales_weight * data["sales"] +
                    self.interaction_weight * (data["pickups"] - data["dropoffs"])
            )
            if priority_items and item_id in priority_items:
                priority *= 1.5  # 优先商品权重增加50%
            item_priorities[item_id] = priority

        sorted_items = sorted(item_priorities.items(), key=lambda x: x[1], reverse=True)

        # 3. 分配商品到货架位置
        zone_capacity = defaultdict(int)  # 记录每个区域已分配的商品数
        max_items_per_zone = max(1, len(sorted_items) // len(sorted_zones) + 1)

        recommendations = {}
        for item_id, _ in sorted_items:
            for zone, _ in sorted_zones:
                if zone_capacity[zone] < max_items_per_zone:
                    recommendations[item_id] = zone
                    zone_capacity[zone] += 1
                    break

        return recommendations

    def get_optimized_layout(self, priority_items: List[str] = None) -> Dict[str, List[str]]:
        """获取优化后的货架布局"""
        recommendations = self.recommend_item_positions(priority_items)
        layout = defaultdict(list)
        for item_id, zone in recommendations.items():
            layout[zone].append(item_id)
        return layout

    def generate_report(self) -> Dict:
        """生成货架优化报告"""
        avg_height = np.mean(self.height_history) if self.height_history else None
        gaze_lower, gaze_upper = self.calculate_gaze_range()
        shelf_scores = self.calculate_shelf_scores()
        optimized_layout = self.get_optimized_layout()

        # 获取库存不足的商品
        low_stock_items = {item_id: data["current_stock"]
                           for item_id, data in self.item_data.items()
                           if data["current_stock"] <= 2}

        return {
            "average_customer_height": avg_height,
            "optimal_gaze_range": (gaze_lower, gaze_upper),
            "shelf_scores": shelf_scores,
            "recommended_layout": optimized_layout,
            "low_stock_items": low_stock_items
        }

    def __del__(self):
        """关闭数据库连接"""
        try:
            self.conn.close()
        except:
            pass


class SmartShelfUI:
    def __init__(self, root):
        self.root = root
        self.root.title("智能货架管理系统")

        self.optimizer = SmartShelfOptimizer(
            camera_height=2.0,
            camera_angle=15,
            shelf_layout={
                "top": (1.7, 2.2),
                "upper_middle": (1.2, 1.7),
                "lower_middle": (0.7, 1.2),
                "bottom": (0.2, 0.7)
            },
            db_file=r"C:\Users\shark\PycharmProjects\AI Homework\smart_shelf.db3"
        )

        # 创建主框架
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(padx=10, pady=10)

        # 按钮区域
        self.button_frame = tk.Frame(self.main_frame)
        self.button_frame.pack(fill=tk.X, pady=10)

        self.generate_report_btn = tk.Button(self.button_frame, text="生成报告", command=self.generate_report)
        self.generate_report_btn.pack(side=tk.LEFT, padx=5)

        self.check_stock_btn = tk.Button(self.button_frame, text="检测商品数量", command=self.check_stock)
        self.check_stock_btn.pack(side=tk.LEFT, padx=5)

        self.operation_btn = tk.Button(self.button_frame, text="商品操作", command=self.show_operation_window)
        self.operation_btn.pack(side=tk.LEFT, padx=5)

        # 报告显示区域
        self.report_frame = tk.Frame(self.main_frame)
        self.report_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.report_text = tk.Text(self.report_frame, height=20, width=80)
        self.report_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = tk.Scrollbar(self.report_frame, command=self.report_text.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.report_text.config(yscrollcommand=self.scrollbar.set)

    def generate_report(self):
        """生成并显示报告"""
        self.report_text.delete(1.0, tk.END)
        report = self.optimizer.generate_report()

        self.report_text.insert(tk.END, "=" * 50 + "\n")
        self.report_text.insert(tk.END, "智能货架优化报告\n")
        self.report_text.insert(tk.END, "=" * 50 + "\n")

        # 处理平均顾客身高为 None 的情况
        avg_height = report.get("average_customer_height")
        if avg_height is not None:
            self.report_text.insert(tk.END, f"平均顾客身高: {avg_height:.2f}米\n")
        else:
            self.report_text.insert(tk.END, "平均顾客身高: 无有效历史数据\n")

        self.report_text.insert(tk.END,
                                f"最佳视线范围: {report['optimal_gaze_range'][0]:.2f}-{report['optimal_gaze_range'][1]:.2f}米\n")

        self.report_text.insert(tk.END, "\n货架区域得分:\n")
        for zone, score in sorted(report["shelf_scores"].items(), key=lambda x: x[1], reverse=True):
            self.report_text.insert(tk.END, f"  - {zone}: {score:.4f}\n")

        self.report_text.insert(tk.END, "\n推荐的商品布局:\n")
        for zone, items in report["recommended_layout"].items():
            self.report_text.insert(tk.END, f"  {zone}: {', '.join(items)}\n")

    def check_stock(self):
        """检测商品数量并显示补货提醒"""
        report = self.optimizer.generate_report()
        # 修改库存不足的判断条件为 current_stock <= 1
        low_stock_items = {item_id: data["current_stock"]
                           for item_id, data in self.optimizer.item_data.items()
                           if data["current_stock"] <= 1}

        if low_stock_items:
            message = "需要补货的商品:\n"
            for item_id, stock in low_stock_items.items():
                message += f"  - {item_id}: 当前库存 {stock}\n"

            messagebox.showwarning("补货提醒", message)
        else:
            messagebox.showinfo("库存检查", "所有商品库存充足")

        # 在底部窗口显示所有商品的剩余数量
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, "所有商品的剩余数量:\n")
        for item_id, data in self.optimizer.item_data.items():
            self.report_text.insert(tk.END, f"  - {item_id}: 当前库存 {data['current_stock']}\n")

    def show_operation_window(self):
        """显示商品操作窗口"""
        # 创建操作窗口
        self.operation_window = tk.Toplevel(self.root)
        self.operation_window.title("商品操作")
        self.operation_window.geometry("400x300")
        self.operation_window.resizable(False, False)

        # 获取数据库中的所有商品ID
        item_ids = list(self.optimizer.item_data.keys())

        # 创建操作窗口中的控件
        tk.Label(self.operation_window, text="商品ID:").grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)

        self.item_id_var = tk.StringVar()
        self.item_id_combobox = ttk.Combobox(self.operation_window, textvariable=self.item_id_var, values=item_ids,
                                             width=25)
        self.item_id_combobox.grid(row=0, column=1, padx=10, pady=10)
        if item_ids:
            self.item_id_combobox.current(0)

        tk.Label(self.operation_window, text="操作类型:").grid(row=1, column=0, padx=10, pady=10, sticky=tk.W)

        self.operation_var = tk.StringVar(value="销售")
        tk.Radiobutton(self.operation_window, text="销售", variable=self.operation_var, value="销售").grid(row=1,
                                                                                                           column=1,
                                                                                                           padx=10,
                                                                                                           pady=10,
                                                                                                           sticky=tk.W)
        tk.Radiobutton(self.operation_window, text="补货", variable=self.operation_var, value="补货").grid(row=1,
                                                                                                           column=1,
                                                                                                           padx=10,
                                                                                                           pady=10,
                                                                                                           sticky=tk.E)

        tk.Label(self.operation_window, text="数量:").grid(row=2, column=0, padx=10, pady=10, sticky=tk.W)

        self.quantity_var = tk.IntVar(value=1)
        self.quantity_spinbox = tk.Spinbox(self.operation_window, from_=1, to=100, textvariable=self.quantity_var,
                                           width=10)
        self.quantity_spinbox.grid(row=2, column=1, padx=10, pady=10, sticky=tk.W)

        # 执行按钮
        self.execute_btn = tk.Button(self.operation_window, text="执行", command=self.execute_operation)
        self.execute_btn.grid(row=3, column=0, columnspan=2, pady=20)

        # 结果显示
        self.result_var = tk.StringVar()
        self.result_label = tk.Label(self.operation_window, textvariable=self.result_var, fg="green")
        self.result_label.grid(row=4, column=0, columnspan=2, pady=10)

    def execute_operation(self):
        """执行商品操作"""
        item_id = self.item_id_var.get()
        operation = self.operation_var.get()
        quantity = self.quantity_var.get()

        if not item_id:
            self.result_var.set("请选择商品ID")
            return

        try:
            if operation == "销售":
                current_stock = self.optimizer.item_data[item_id]["current_stock"]
                if current_stock < quantity:
                    self.result_var.set(f"操作失败: 库存不足 (当前库存: {current_stock})")
                    return

                self.optimizer.record_sale(item_id, quantity)
                self.result_var.set(f"成功记录销售 {quantity} 件 {item_id}")
            elif operation == "补货":
                self.optimizer.restock_item(item_id, quantity)
                self.result_var.set(f"成功补货 {quantity} 件 {item_id}")

            # 刷新报告
            self.generate_report()

        except Exception as e:
            self.result_var.set(f"操作失败: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SmartShelfUI(root)
    root.mainloop()