import numpy as np
import random
import json
import heapq
import pandas as pd # Нужно для удобного экспорта в CSV
from enum import Enum

# --- КОНСТАНТЫ ---
GRID_SIZE = 30
CELL_SIZE = 20

COST_NORMAL = 1
COST_SMOKE = 5
COST_FIRE = float('inf')
COST_WALL = float('inf')

class CellState(Enum):
    NORMAL = 0
    SMOKE = 1
    FIRE = 2
    BURNT = 3
    WALL = 4

class AgentType(Enum):
    FIRE_FIGHTER = 0

class SimulationEngine:
    def __init__(self, rows=GRID_SIZE, cols=GRID_SIZE):
        self.rows = rows
        self.cols = cols
        self.grid = np.zeros((rows, cols), dtype=int)
        self.agents = [] 
        self.time_step = 0
        self.active = False
        self.fire_intensity = 1 
        
        # История для графиков (простая)
        self.history = []
        # Полный лог для CSV (детальная)
        self.full_log = []

    # ... (Методы toggle_cell, is_occupied, add_agent, remove_agent - БЕЗ ИЗМЕНЕНИЙ) ...
    def toggle_cell(self, r, c):
        if self.grid[r][c] == CellState.NORMAL.value: self.grid[r][c] = CellState.FIRE.value
        elif self.grid[r][c] == CellState.FIRE.value: self.grid[r][c] = CellState.WALL.value
        else: self.grid[r][c] = CellState.NORMAL.value

    def is_occupied(self, r, c):
        for a in self.agents:
            if a['r'] == r and a['c'] == c: return True
        return False

    def add_agent(self, r, c):
        if self.grid[r][c] in [CellState.WALL.value, CellState.FIRE.value]: return
        if self.is_occupied(r, c): return
        self.agents.append({
            'r': r, 'c': c, 'type': AgentType.FIRE_FIGHTER, 
            'path': [], 'waypoints': []  
        })

    def remove_agent(self, r, c):
        self.agents = [a for a in self.agents if not (a['r'] == r and a['c'] == c)]

    def get_fire_area(self):
        return np.sum(self.grid == CellState.FIRE.value)

    # ... (Методы find_path_astar, get_optimal_strategy, predict_future_grid - БЕЗ ИЗМЕНЕНИЙ) ...
    # Копируйте их из предыдущего ответа, они работают отлично.
    def find_path_astar(self, start, target, avoid_obstacles=None):
        sr, sc = start; tr, tc = target
        obstacles_set = set(avoid_obstacles) if avoid_obstacles else set()
        if target in obstacles_set: obstacles_set.remove(target)
        queue = [(0, sr, sc, [])]; visited = {}
        while queue:
            cost, r, c, path = heapq.heappop(queue)
            if r == tr and c == tc: return path
            if (r, c) in visited and visited[(r,c)] <= cost: continue
            visited[(r,c)] = cost
            for dr, dc in [(-1,0), (1,0), (0,-1), (0,1)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    cell_val = self.grid[nr][nc]
                    move_cost = COST_NORMAL
                    if cell_val == CellState.SMOKE.value: move_cost = COST_SMOKE
                    elif cell_val == CellState.WALL.value or cell_val == CellState.BURNT.value: move_cost = COST_WALL
                    elif cell_val == CellState.FIRE.value:
                        if nr == tr and nc == tc: move_cost = COST_NORMAL
                        else: move_cost = COST_FIRE
                    if (nr, nc) in obstacles_set: move_cost = COST_WALL
                    if move_cost < float('inf'):
                        new_cost = cost + move_cost
                        heuristic = abs(nr - tr) + abs(nc - tc)
                        heapq.heappush(queue, (new_cost + heuristic, nr, nc, path + [(nr, nc)]))
        return []

    def get_optimal_strategy(self):
        strategy = []
        attack_points = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == CellState.FIRE.value:
                    for dr, dc in [(-1,0), (1,0), (0,-1), (0,1)]:
                        nr, nc = r+dr, c+dc
                        if 0 <= nr < self.rows and 0 <= nc < self.cols:
                            if self.grid[nr][nc] == CellState.NORMAL.value:
                                attack_points.append((nr, nc))
        unique_targets = list(set(attack_points))
        if not unique_targets: return []
        for agent in self.agents:
            start = (agent['r'], agent['c'])
            best_target = None; min_dist = float('inf')
            candidates = sorted(unique_targets, key=lambda t: abs(start[0]-t[0]) + abs(start[1]-t[1]))[:3]
            best_path = []
            for t in candidates:
                path = self.find_path_astar(start, t)
                if path and len(path) < min_dist:
                    min_dist = len(path); best_target = t; best_path = path
            if best_target: strategy.append({'start': start, 'path': best_path})
        return strategy

    def predict_future_grid(self, steps=20):
        temp_grid = self.grid.copy()
        for _ in range(steps):
            next_grid = temp_grid.copy()
            for r in range(self.rows):
                for c in range(self.cols):
                    if temp_grid[r][c] == CellState.FIRE.value:
                        neighbors = [(-1,0), (1,0), (0,-1), (0,1)]
                        for dr, dc in neighbors:
                            nr, nc = r+dr, c+dc
                            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                                if temp_grid[nr][nc] == CellState.NORMAL.value:
                                    if random.random() < 0.1: next_grid[nr][nc] = CellState.FIRE.value
            temp_grid = next_grid
        return temp_grid

    # --- STEP ---
    def step(self):
        if not self.active: return
        self.time_step += 1
        
        area = self.get_fire_area()
        self.history.append(area)
        
        # --- ЛОГИРОВАНИЕ ДЛЯ ОТЧЕТА ---
        # Сохраняем позиции агентов строкой "(r,c); (r,c)"
        agents_pos_str = "; ".join([f"({a['r']},{a['c']})" for a in self.agents])
        self.full_log.append({
            'step': self.time_step,
            'fire_area': area,
            'agents_count': len(self.agents),
            'agents_positions': agents_pos_str
        })
        # -----------------------------
        
        new_grid = self.grid.copy()

        # 1. Огонь
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == CellState.FIRE.value:
                    if random.random() < 0.02: new_grid[r][c] = CellState.BURNT.value
                    for dr, dc in [(-1,0), (1,0), (0,-1), (0,1)]:
                        nr, nc = r+dr, c+dc
                        if 0 <= nr < self.rows and 0 <= nc < self.cols:
                            if self.grid[nr][nc] == CellState.NORMAL.value:
                                if random.random() < 0.08: new_grid[nr][nc] = CellState.FIRE.value
                elif self.grid[r][c] == CellState.SMOKE.value:
                    if random.random() < 0.1: new_grid[r][c] = CellState.NORMAL.value
        
        # 2. Агенты
        occupied_positions = {(a['r'], a['c']) for a in self.agents}
        for agent in self.agents:
            r, c = agent['r'], agent['c']
            fire_nearby = False
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.rows and 0 <= nc < self.cols:
                        if new_grid[nr][nc] == CellState.FIRE.value:
                            fire_nearby = True
                            if random.random() < 0.8: new_grid[nr][nc] = CellState.SMOKE.value
            
            if not fire_nearby:
                if agent['waypoints']:
                    target = agent['waypoints'][0]
                    if (r, c) == target:
                        agent['waypoints'].pop(0); agent['path'] = []
                        if agent['waypoints']: target = agent['waypoints'][0]
                        else: target = None
                    if target and not agent['path']:
                        agent['path'] = self.find_path_astar((r,c), target)
                
                if agent['path']:
                    next_step = agent['path'][0]; nr, nc = next_step
                    is_blocked_by_agent = (nr, nc) in occupied_positions and (nr, nc) != (r, c)
                    is_passable = new_grid[nr][nc] not in [CellState.WALL.value, CellState.FIRE.value] or (new_grid[nr][nc] == CellState.FIRE.value and not agent['path'][1:])

                    if not is_blocked_by_agent and is_passable:
                        occupied_positions.remove((r, c)); occupied_positions.add((nr, nc))
                        agent['r'] = nr; agent['c'] = nc; agent['path'].pop(0)
                    elif is_blocked_by_agent:
                        target = agent['waypoints'][0] if agent['waypoints'] else agent['path'][-1]
                        new_detour = self.find_path_astar((r,c), target, avoid_obstacles=occupied_positions)
                        if new_detour: agent['path'] = new_detour
                    else: agent['path'] = []

        self.grid = new_grid

    # --- ЭКСПОРТ ---
    def export_log_to_csv(self, filename):
        if not self.full_log: return False
        try:
            df = pd.DataFrame(self.full_log)
            df.to_csv(filename, index=False)
            return True
        except Exception as e:
            print(e)
            return False
            
    # Save/Load
    def save_map_to_json(self, filename):
        clean_agents = [{'r': a['r'], 'c': a['c'], 'type': a['type'], 'path': [], 'waypoints': a['waypoints']} for a in self.agents]
        data = {"rows": self.rows, "cols": self.cols, "grid": self.grid.tolist(), "agents": clean_agents}
        with open(filename, 'w') as f: json.dump(data, f)

    def load_map_from_json(self, filename):
        with open(filename, 'r') as f: data = json.load(f)
        self.rows = data["rows"]
        self.cols = data["cols"]
        self.grid = np.array(data["grid"])
        self.agents = data["agents"]
        for a in self.agents: 
            a['path'] = []; 
            if 'waypoints' not in a: a['waypoints'] = []
        self.history = []
        self.full_log = []