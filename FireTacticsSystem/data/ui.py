import sys
import numpy as np
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFrame, QSplitter, 
                             QFileDialog, QMessageBox)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen

from simulation import SimulationEngine, CellState, GRID_SIZE, CELL_SIZE
from ml_module import MLModule

# MapWidget оставляем прежним (он работает корректно)
class MapWidget(QWidget):
    def __init__(self, simulation, mode="REAL"):
        super().__init__()
        self.sim = simulation
        self.mode = mode
        self.setFixedSize(GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE)
        self.selected_agent_idx = None; self.predicted_grid = None
        self.cached_strategy = []; self.last_pred_step = -1

    def update_size(self): self.setFixedSize(self.sim.cols * CELL_SIZE, self.sim.rows * CELL_SIZE); self.update()

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        if self.mode == "REAL":
            self.draw_grid(painter, self.sim.grid); self.draw_agents_and_routes(painter)
        elif self.mode == "PREDICTION":
            if self.sim.time_step != self.last_pred_step or self.predicted_grid is None:
                self.predicted_grid = self.sim.predict_future_grid(steps=15)
                self.cached_strategy = self.sim.get_optimal_strategy()
                self.last_pred_step = self.sim.time_step
            self.draw_grid(painter, self.predicted_grid, is_prediction=True)
            self.draw_optimal_routes(painter); self.draw_agents_simple(painter)

    def draw_grid(self, painter, grid, is_prediction=False):
        painter.setPen(QPen(Qt.lightGray, 1)); rows, cols = grid.shape
        for r in range(rows):
            for c in range(cols):
                state = grid[r][c]; color = Qt.white
                if state == CellState.FIRE.value: color = QColor(139, 0, 0) if is_prediction else QColor(255, 69, 0)
                elif state == CellState.SMOKE.value: color = QColor(220, 220, 220)
                elif state == CellState.BURNT.value: color = QColor(80, 80, 80)
                elif state == CellState.WALL.value: color = Qt.black
                painter.setBrush(QBrush(color)); painter.drawRect(c * CELL_SIZE, r * CELL_SIZE, CELL_SIZE, CELL_SIZE)

    def draw_agents_and_routes(self, painter):
        for i, agent in enumerate(self.sim.agents):
            pen = QPen(QColor(0, 0, 255), 2, Qt.SolidLine) if i == self.selected_agent_idx else QPen(QColor(0, 0, 255, 50), 1, Qt.DashLine)
            painter.setPen(pen)
            points = [(agent['c'], agent['r'])] + [(p[1], p[0]) for p in agent.get('path', [])] + [(wp[1], wp[0]) for wp in agent['waypoints']]
            for j in range(len(points) - 1):
                p1 = points[j]; p2 = points[j+1]
                painter.drawLine(p1[0]*CELL_SIZE+10, p1[1]*CELL_SIZE+10, p2[0]*CELL_SIZE+10, p2[1]*CELL_SIZE+10)
        for i, agent in enumerate(self.sim.agents):
            c, r = agent['c'], agent['r']
            if i == self.selected_agent_idx: painter.setPen(QPen(Qt.yellow, 3)); painter.setBrush(Qt.NoBrush); painter.drawEllipse(c*CELL_SIZE+2, r*CELL_SIZE+2, CELL_SIZE-4, CELL_SIZE-4)
            painter.setPen(Qt.black); painter.setBrush(QBrush(Qt.blue)); painter.drawEllipse(c*CELL_SIZE+4, r*CELL_SIZE+4, CELL_SIZE-8, CELL_SIZE-8)

    def draw_optimal_routes(self, painter):
        pen = QPen(QColor(0, 255, 0, 200), 2, Qt.SolidLine); painter.setPen(pen)
        for plan in self.cached_strategy:
            path = plan['path']
            if not path: continue
            start_r, start_c = plan['start']; prev_x = start_c*CELL_SIZE+10; prev_y = start_r*CELL_SIZE+10
            for (r, c) in path: curr_x = c*CELL_SIZE+10; curr_y = r*CELL_SIZE+10; painter.drawLine(prev_x, prev_y, curr_x, curr_y); prev_x, prev_y = curr_x, curr_y
            end_r, end_c = path[-1]; painter.setBrush(QBrush(QColor(0, 255, 0, 150))); painter.setPen(Qt.NoPen); painter.drawEllipse(end_c*CELL_SIZE+6, end_r*CELL_SIZE+6, CELL_SIZE-12, CELL_SIZE-12)

    def draw_agents_simple(self, painter):
        painter.setBrush(QBrush(QColor(0, 0, 255, 80))); painter.setPen(Qt.NoPen)
        for agent in self.sim.agents: painter.drawEllipse(agent['c']*CELL_SIZE+5, agent['r']*CELL_SIZE+5, CELL_SIZE-10, CELL_SIZE-10)

    def mousePressEvent(self, event):
        if self.mode == "REAL":
            c = event.x() // CELL_SIZE; r = event.y() // CELL_SIZE
            if 0 <= r < self.sim.rows and 0 <= c < self.sim.cols:
                if event.button() == Qt.LeftButton:
                    clicked = -1
                    for i, a in enumerate(self.sim.agents): 
                        if a['r'] == r and a['c'] == c: clicked = i; break
                    if clicked != -1: self.selected_agent_idx = clicked
                    else: 
                        if self.selected_agent_idx is not None: self.selected_agent_idx = None
                        else: self.sim.toggle_cell(r, c)
                elif event.button() == Qt.RightButton:
                    if self.selected_agent_idx is not None:
                        if self.selected_agent_idx < len(self.sim.agents): self.sim.agents[self.selected_agent_idx]['waypoints'].append((r, c))
                    else:
                        if self.sim.is_occupied(r, c): self.sim.remove_agent(r, c)
                        else: self.sim.add_agent(r, c)
                self.update()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Система анализа и оценки тактики тушения")
        self.setGeometry(100, 100, 1300, 750)
        self.sim = SimulationEngine()
        self.ml = MLModule()
        self.ml.train() 
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_simulation)
        self.timer.start(300) 

    def init_ui(self):
        central_widget = QWidget(); self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Панель управления
        control_panel = QFrame(); control_panel.setFixedWidth(290)
        control_layout = QVBoxLayout(control_panel)
        
        lbl_title = QLabel("<h2>Анализ тактики</h2>")
        lbl_instr = QLabel("<b>ЛКМ(Юнит)</b>: Выбрать\n<b>ЛКМ(Пусто)</b>: Снять / Огонь\n<b>ПКМ</b>: Маршрут / Создать\n")
        
        btn_start = QPushButton("▶ Старт / Пауза")
        btn_start.clicked.connect(self.toggle_sim)
        
        btn_reset = QPushButton("↺ Сброс")
        btn_reset.clicked.connect(self.reset_sim)
        
        btn_load = QPushButton("📂 Загрузить план")
        btn_load.clicked.connect(self.load_map_dialog)
        
        btn_save = QPushButton("💾 Сохранить план")
        btn_save.clicked.connect(self.save_map_dialog)
        
        btn_csv = QPushButton("📑 Экспорт лога (CSV)")
        btn_csv.clicked.connect(self.export_csv)
        
        btn_report = QPushButton("📊 Оценка поведения")
        btn_report.clicked.connect(self.show_report)
        btn_report.setStyleSheet("background-color: #d4edda; color: #155724; font-weight: bold; padding: 5px;")
        
        self.lbl_stats = QLabel("Статистика: ожидание...")
        self.lbl_stats.setWordWrap(True)
        self.lbl_risk = QLabel("Риск: -")
        
        control_layout.addWidget(lbl_title); control_layout.addWidget(lbl_instr)
        control_layout.addSpacing(10)
        control_layout.addWidget(btn_start); control_layout.addWidget(btn_reset)
        control_layout.addSpacing(10)
        control_layout.addWidget(btn_load); control_layout.addWidget(btn_save)
        control_layout.addWidget(btn_csv)
        control_layout.addSpacing(10)
        control_layout.addWidget(btn_report)
        control_layout.addStretch()
        control_layout.addWidget(QLabel("<b>Метрики в реальном времени:</b>"))
        control_layout.addWidget(self.lbl_stats)
        control_layout.addWidget(self.lbl_risk)
        
        # Окна
        splitter = QSplitter(Qt.Horizontal)
        self.map_real = MapWidget(self.sim, mode="REAL")
        container_real = QWidget(); l_real = QVBoxLayout(container_real)
        l_real.addWidget(QLabel("<h3>Оперативная обстановка (Факт)</h3>")); l_real.addWidget(self.map_real); l_real.addStretch()
        
        self.map_pred = MapWidget(self.sim, mode="PREDICTION")
        container_pred = QWidget(); l_pred = QVBoxLayout(container_pred)
        l_pred.addWidget(QLabel("<h3>Прогноз распространения</h3>")); l_pred.addWidget(self.map_pred); l_pred.addStretch()

        splitter.addWidget(container_real); splitter.addWidget(container_pred)
        main_layout.addWidget(control_panel); main_layout.addWidget(splitter)

    def toggle_sim(self): self.sim.active = not self.sim.active
    
    def reset_sim(self):
        self.sim = SimulationEngine(self.sim.rows, self.sim.cols)
        self.map_real.sim = self.sim; self.map_pred.sim = self.sim
        self.map_real.selected_agent_idx = None; self.map_real.update(); self.map_pred.update()
        self.lbl_stats.setText("Сброс")

    def load_map_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Открыть', '.', "JSON Files (*.json)")
        if fname: self.sim.load_map_from_json(fname); self.map_real.update_size(); self.map_pred.update_size()

    def save_map_dialog(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Сохранить', '.', "JSON Files (*.json)")
        if fname: self.sim.save_map_to_json(fname)

    def export_csv(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Сохранить лог', '.', "CSV Files (*.csv)")
        if fname:
            success = self.sim.export_log_to_csv(fname)
            if success: QMessageBox.information(self, "Экспорт", "Лог успешно сохранен!")
            else: QMessageBox.warning(self, "Ошибка", "Нет данных для экспорта.")

    def show_report(self):
        if not self.sim.history:
            QMessageBox.warning(self, "Нет данных", "Нет данных для анализа")
            return
        
        real_data = self.sim.history
        
        # --- 1. ВЫЧИСЛЕНИЕ МЕТРИК ---
        max_area = max(real_data)
        time_peak = real_data.index(max_area)
        current_area = real_data[-1]
        
        # Интеграл площади (сумма) - ущерб
        auc_real = sum(real_data)
        
        # --- 2. ML ПРОГНОЗ И РИСК ---
        units = len(self.sim.agents)
        if units == 0: units = 1
        
        pred_time, pred_risk = self.ml.predict(max_area, units, self.sim.fire_intensity)
        predicted_steps = int(pred_time)
        
        risk_label = "ВЫСОКИЙ" if pred_risk == 1 else "Низкий"
        risk_color = "red" if pred_risk == 1 else "green"

        # --- 3. ИДЕАЛЬНАЯ КРИВАЯ ---
        ideal_data = real_data[:time_peak+1]
        if predicted_steps > 0:
            decay = max_area / predicted_steps
            val = max_area
            for _ in range(predicted_steps + 5):
                val -= decay
                if val < 0: val = 0
                ideal_data.append(val)
                if val == 0: break
        
        # --- 4. ОЦЕНКА ЭФФЕКТИВНОСТИ ---
        # Считаем отклонение факта от идеала (после пика)
        # Если факт спадает медленнее идеала -> эффективность падает
        
        auc_ideal = sum(ideal_data)
        # Простая формула эффективности: Отношение площадей (инвертированное, т.к. меньше площадь = лучше)
        # Если auc_real == auc_ideal -> 100%. Если auc_real > auc_ideal -> <100%
        efficiency = (auc_ideal / auc_real) * 100 if auc_real > 0 else 100
        efficiency = min(100, efficiency) # Не более 100%

        # --- 5. ГРАФИК ---
        plt.figure("Аналитический отчет", figsize=(10, 7))
        plt.plot(real_data, label='ФАКТ (Реальность)', color='red', linewidth=3)
        plt.plot(ideal_data, label='ПЛАН (ML-прогноз)', color='green', linestyle='--', linewidth=2)
        
        # Текстовый блок с метриками
        info_text = (
            f"Эффективность тактики: {efficiency:.1f}%\n"
            f"Риск развития: {risk_label}\n"
            f"---------------------------\n"
            f"Время до пика: {time_peak} ш.\n"
            f"Время прогноза тушения: {predicted_steps} ш.\n"
            f"Общий ущерб (AUC): {auc_real}"
        )
        
        plt.figtext(0.15, 0.65, info_text, fontsize=11, 
                    bbox=dict(facecolor='white', alpha=0.9, edgecolor='black'))

        plt.title(f"Оценка поведения подразделений\nМакс. площадь: {max_area} | Сил: {units}")
        plt.xlabel("Время (шаги симуляции)")
        plt.ylabel("Площадь горения (клетки)")
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.legend()
        plt.show()

    def update_simulation(self):
        if self.sim.active: self.sim.step()
        self.map_real.update(); self.map_pred.update()
        
        # Обновление метрик в боковой панели
        area = self.sim.get_fire_area()
        units = len(self.sim.agents)
        if self.sim.history:
            peak = max(self.sim.history)
            auc = sum(self.sim.history)
        else: peak = 0; auc = 0
            
        self.lbl_stats.setText(f"Время: {self.sim.time_step}\nПлощадь: {area}\nПик: {peak}\nУщерб(AUC): {auc}")
        
        # Обновление риска (реже, чтобы не мигало)
        if self.sim.time_step % 10 == 0 and area > 0:
            _, risk = self.ml.predict(area, units, self.sim.fire_intensity)
            r_str = "ВЫСОКИЙ" if risk == 1 else "Низкий"
            col = "red" if risk == 1 else "green"
            self.lbl_risk.setText(f"Риск (ML): <span style='color:{col}; font-weight:bold'>{r_str}</span>")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())