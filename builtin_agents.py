"""Built-in agent definitions for AgentGenerator."""

AGENTS = [
    {
        "name": "Competitive Agent",
        "icon": "trophy",
        "description": "Uses all 10 trap types with prediction, energy tiers, and healing.",
        "code": '''# ruff: disable[F403]
# ruff: disable[F405]
from api import *
import math
import random

MIN_COORDINATE = -220
MAX_COORDINATE = 220
PLAYER_RADIUS = 13.5
FIELD_SIZE = 440
MAX_HEALTH = 5
MAX_HEAL_COUNT = 2
JUST_OUTSIDE = 240

HEAL_COST_BY_PHASE = {0: 25, 1: 35, 2: 45, 3: 52, 4: 60, 5: 65}
ENERGY_CAP_BY_PHASE = {0: 35, 1: 50, 2: 60, 3: 70, 4: 77, 5: 85}
TRAP_COST = {1: 5, 2: 15, 3: 13, 4: 20, 5: 5, 6: 20, 7: 20, 8: 15, 9: 12, 10: 15}
PHASE_SPEED_FACTOR = {0: 0.3, 1: 0.35, 2: 0.4, 3: 0.45, 4: 0.5, 5: 0.55}
ALL_DIRS = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]
GRID_POSITIONS = [(x, y) for x in range(-200, 201, 40) for y in range(-200, 201, 40)]


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def predict(pos, vel, t):
    return Vector2(clamp(pos.x + vel.x * t, -225, 225), clamp(pos.y + vel.y * t, -225, 225))


def nearest_open_grid(opp_pos, used_spots):
    best = None
    best_d = float("inf")
    for gx, gy in GRID_POSITIONS:
        spot = (round(gx / 40), round(gy / 40))
        if spot in used_spots:
            continue
        d = distance(opp_pos, Vector2(gx, gy))
        if d < best_d:
            best_d = d
            best = (gx, gy)
    if best is None:
        return (clamp(opp_pos.x, -200, 200), clamp(opp_pos.y, -200, 200))
    return best


def run(client):
    client.print_api_errors = False
    heal_count = 0
    previous_print_time = 300.0
    pos_history = []
    used_trap_spots = set()
    last_trap_time = {}

    while True:
        remaining = 300.0 - client.get_elapsed_time()
        phase = client.get_phase()
        my_energy = client.get_my_energy()
        my_health = client.get_my_health()
        energy_cap = ENERGY_CAP_BY_PHASE.get(phase, 85)
        heal_cost = HEAL_COST_BY_PHASE.get(phase, 65)
        opp_pos = client.get_opponent_player_position()
        opp_vel = client.get_opponent_player_velocity()
        opp_combo = client.get_opponent_combo()
        ball_pos = client.get_opponent_energy_ball_position()
        speed = math.hypot(opp_vel.x, opp_vel.y)
        available = client.get_available_traps()
        pf = PHASE_SPEED_FACTOR.get(phase, 0.4)

        pos_history.append((opp_pos.x, opp_pos.y))
        if len(pos_history) > 5:
            pos_history.pop(0)

        if len(pos_history) >= 3:
            dx_sum = sum(pos_history[i][0] - pos_history[i - 1][0] for i in range(1, len(pos_history)))
            dy_sum = sum(pos_history[i][1] - pos_history[i - 1][1] for i in range(1, len(pos_history)))
            avg_dx = dx_sum / (len(pos_history) - 1)
            avg_dy = dy_sum / (len(pos_history) - 1)
            trend_speed = math.hypot(avg_dx, avg_dy)
            trend_dir = Vector2(avg_dx / trend_speed if trend_speed > 0 else 0, avg_dy / trend_speed if trend_speed > 0 else 0)
        else:
            trend_speed = speed
            trend_dir = opp_vel

        need_heal = my_health <= 1 and heal_count < MAX_HEAL_COUNT and my_energy >= heal_cost
        if need_heal or (my_health <= 2 and heal_count < MAX_HEAL_COUNT and my_energy >= heal_cost and my_energy >= energy_cap * 0.6):
            result = client.heal()
            if not isinstance(result, ApiError):
                heal_count += 1

        dist_to_ball = distance(opp_pos, ball_pos)
        near_edge = abs(opp_pos.x) > 180 or abs(opp_pos.y) > 180
        at_corner = abs(opp_pos.x) > 200 or abs(opp_pos.y) > 200
        energy_high = my_energy >= energy_cap * 0.85
        energy_mid = my_energy >= 15

        if energy_high and (my_health > 1 or heal_count >= MAX_HEAL_COUNT):
            sweep = Direction.UP if abs(trend_dir.y) > abs(trend_dir.x) else Direction.LEFT
            if 6 in available and 7 in available:
                client.spawn_trap6(sweep, clamp(180 + speed * 0.2, 150, 250))
                ripple_pos = predict(opp_pos, opp_vel, 0.3)
                client.spawn_trap7(Vector2(clamp(ripple_pos.x, -400, 400), clamp(ripple_pos.y, -280, 280)), clamp(100 + speed * 0.3, 100, 200))
            if 4 in available and dist_to_ball < 200:
                push_away = Direction.RIGHT if opp_pos.x < 0 else Direction.LEFT
                if abs(opp_pos.y) > 80:
                    push_away = Direction.UP if opp_pos.y > 0 else Direction.DOWN
                client.spawn_trap4(Vector2(clamp(opp_pos.x, -100, 100), clamp(opp_pos.y, -100, 100)), push_away)
            if 8 in available:
                if abs(opp_pos.x) < 80:
                    client.spawn_trap8(Vector2(-220, opp_pos.y - 60), Vector2(220, opp_pos.y + 60))
                else:
                    client.spawn_trap8(Vector2(opp_pos.x - 60, -220), Vector2(opp_pos.x + 60, 220))
            if 10 in available:
                dx = 1.0 if opp_vel.x > 0 else -1.0 if opp_vel.x < 0 else (1.0 if opp_pos.x < 0 else -1.0)
                dy = 0.3 if opp_vel.y >= 0 else -0.3
                client.spawn_trap10(Vector2(clamp(opp_pos.x - dx * 30, -250, 250), clamp(opp_pos.y, -280, 280)), Vector2(dx, -0.3), Vector2(dx, 0.0), Vector2(dx, 0.3))

        elif energy_mid:
            if trend_speed > 40:
                pred_t = clamp(0.3 + trend_speed / 300 + pf * 0.5, 0.4, 1.5)
                pred = predict(opp_pos, opp_vel, pred_t)
                if 2 in available and trend_speed > 60:
                    delay = clamp(0.5 + trend_speed / 400, 0.8, 2.0)
                    radius = clamp(60 + trend_speed * 0.6, 80, 150)
                    client.spawn_trap2(delay, radius)
                if 9 in available and trend_speed > 80:
                    start_x = 220 if opp_pos.x < 0 else -220
                    air = clamp(distance(opp_pos, pred) / 140 + 0.3, 0.8, 2.5)
                    client.spawn_trap9(Vector2(start_x, opp_pos.y), pred, air)
                gx, gy = nearest_open_grid(pred, used_trap_spots)
                if 1 in available:
                    client.spawn_trap1(Vector2(gx, gy))
                    used_trap_spots.add((round(gx / 40), round(gy / 40)))
                if 5 in available:
                    client.spawn_trap5(Vector2(clamp(pred.x, -150, 150), clamp(pred.y, -150, 150)))

            if dist_to_ball < 200:
                if 1 in available:
                    client.spawn_trap1(Vector2(clamp(ball_pos.x, -225, 225), clamp(ball_pos.y, -225, 225)))
                if 5 in available:
                    sx = clamp(ball_pos.x, -150, 150)
                    sy = clamp(ball_pos.y, -150, 150)
                    client.spawn_trap5(Vector2(sx, sy))
                    client.spawn_trap5(Vector2(clamp(opp_pos.x, -150, 150), clamp(opp_pos.y, -150, 150)))

            if near_edge and 3 in available:
                toward_dir = Vector2(-opp_pos.x, -opp_pos.y)
                mag = math.hypot(toward_dir.x, toward_dir.y)
                if mag > 0:
                    toward_dir = Vector2(toward_dir.x / mag, toward_dir.y / mag)
                client.spawn_trap3(Vector2(clamp(opp_pos.x, -220, 220), clamp(opp_pos.y, -220, 220)), toward_dir, clamp(150 + speed * 0.5, 150, 300))

            if at_corner and 10 in available:
                dx = 1.0 if trend_dir.x >= 0 else -1.0
                dy = clamp(trend_dir.y, -0.5, 0.5)
                client.spawn_trap10(
                    Vector2(clamp(opp_pos.x - dx * 40, -250, 250), clamp(opp_pos.y, -280, 280)),
                    Vector2(dx, dy - 0.3), Vector2(dx, dy), Vector2(dx, dy + 0.3),
                )

        elif my_energy >= TRAP_COST.get(1, 99):
            if 1 in available:
                near_x = clamp(opp_pos.x + random.uniform(-35, 35), -225, 225)
                near_y = clamp(opp_pos.y + random.uniform(-35, 35), -225, 225)
                client.spawn_trap1(Vector2(near_x, near_y))
            if 5 in available and my_energy >= TRAP_COST[5]:
                sx = clamp(ball_pos.x if dist_to_ball < 250 else opp_pos.x, -150, 150)
                sy = clamp(ball_pos.y if dist_to_ball < 250 else opp_pos.y, -150, 150)
                client.spawn_trap5(Vector2(sx, sy))

        if remaining <= previous_print_time - 2.0:
            print(f"Time: {remaining:.1f}s | Phase: {phase} | HP: {my_health} | Energy: {my_energy}/{energy_cap}")
            print(f"Opp: ({opp_pos.x:.0f}, {opp_pos.y:.0f}) | Speed: {speed:.0f} | Ball: {dist_to_ball:.0f}")
            print("---")
            previous_print_time = remaining
'''
    },
    {
        "name": "Energy Denier",
        "icon": "bolt.circle",
        "description": "Focuses on denying opponent energy balls and breaking combos.",
        "code": '''# ruff: disable[F403]
# ruff: disable[F405]
from api import *
import math

MIN_COORDINATE = -220
MAX_COORDINATE = 220
PLAYER_RADIUS = 13.5
FIELD_SIZE = 440
MAX_HEALTH = 5
MAX_HEAL_COUNT = 2

HEAL_COST_BY_PHASE = {0: 25, 1: 35, 2: 45, 3: 52, 4: 60, 5: 65}
ENERGY_CAP_BY_PHASE = {0: 35, 1: 50, 2: 60, 3: 70, 4: 77, 5: 85}
TRAP_COST = {1: 5, 2: 15, 3: 13, 4: 20, 5: 5, 6: 20, 7: 20, 8: 15, 9: 12, 10: 15}
ALL_DIRS = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def run(client):
    client.print_api_errors = False
    heal_count = 0
    previous_print_time = 300.0
    prev_ball_pos = None
    ball_vel_x = 0.0
    ball_vel_y = 0.0
    last_combo_break_time = 0.0
    fence_active = False

    while True:
        remaining = 300.0 - client.get_elapsed_time()
        phase = client.get_phase()
        my_energy = client.get_my_energy()
        my_health = client.get_my_health()
        energy_cap = ENERGY_CAP_BY_PHASE.get(phase, 85)
        heal_cost = HEAL_COST_BY_PHASE.get(phase, 65)
        opp_pos = client.get_opponent_player_position()
        opp_vel = client.get_opponent_player_velocity()
        opp_combo = client.get_opponent_combo()
        ball_pos = client.get_opponent_energy_ball_position()
        speed = math.hypot(opp_vel.x, opp_vel.y)
        available = client.get_available_traps()

        if prev_ball_pos:
            ball_vel_x = ball_pos.x - prev_ball_pos.x
            ball_vel_y = ball_pos.y - prev_ball_pos.y
        prev_ball_pos = Vector2(ball_pos.x, ball_pos.y)
        ball_speed = math.hypot(ball_vel_x, ball_vel_y)

        if my_health <= 1 and heal_count < MAX_HEAL_COUNT and my_energy >= heal_cost:
            result = client.heal()
            if not isinstance(result, ApiError):
                heal_count += 1

        dist_to_ball = distance(opp_pos, ball_pos)

        if opp_combo >= 2:
            if remaining - last_combo_break_time > 1.5:
                if 6 in available:
                    sweep_dir = Direction.UP if abs(opp_pos.y) < abs(opp_pos.x) else Direction.LEFT
                    if ball_pos.y < opp_pos.y:
                        sweep_dir = Direction.DOWN
                    elif ball_pos.y > opp_pos.y:
                        sweep_dir = Direction.UP
                    client.spawn_trap6(sweep_dir, 250.0)
                    last_combo_break_time = remaining
                if 4 in available and dist_to_ball < 150:
                    push = Direction.RIGHT if opp_pos.x < ball_pos.x else Direction.LEFT
                    client.spawn_trap4(Vector2(clamp(opp_pos.x, -100, 100), clamp(opp_pos.y, -100, 100)), push)
                if 7 in available:
                    cx = clamp(opp_pos.x, -400, 400)
                    cy = clamp(opp_pos.y, -280, 280)
                    client.spawn_trap7(Vector2(cx, cy), 220.0)
                if 5 in available:
                    client.spawn_trap5(Vector2(clamp(ball_pos.x, -150, 150), clamp(ball_pos.y, -150, 150)))
                    client.spawn_trap5(Vector2(clamp(opp_pos.x, -150, 150), clamp(opp_pos.y, -150, 150)))
            continue

        if dist_to_ball < 250:
            if 8 in available and not fence_active and dist_to_ball < 180:
                if abs(opp_pos.x - ball_pos.x) > abs(opp_pos.y - ball_pos.y):
                    mid_y = (opp_pos.y + ball_pos.y) / 2
                    client.spawn_trap8(Vector2(-220, clamp(mid_y - 40, -220, 220)), Vector2(220, clamp(mid_y + 40, -220, 220)))
                else:
                    mid_x = (opp_pos.x + ball_pos.x) / 2
                    client.spawn_trap8(Vector2(clamp(mid_x - 40, -220, 220), -220), Vector2(clamp(mid_x + 40, -220, 220), 220))
                fence_active = True

            if 1 in available:
                bx = clamp(ball_pos.x, -225, 225)
                by = clamp(ball_pos.y, -225, 225)
                client.spawn_trap1(Vector2(bx, by))

            if 5 in available:
                bx = clamp(ball_pos.x, -150, 150)
                by = clamp(ball_pos.y, -150, 150)
                client.spawn_trap5(Vector2(bx, by))
                ox = clamp(opp_pos.x, -150, 150)
                oy = clamp(opp_pos.y, -150, 150)
                client.spawn_trap5(Vector2(ox, oy))

            if 9 in available and dist_to_ball < 150:
                bx = clamp(ball_pos.x, -225, 225)
                by = clamp(ball_pos.y, -225, 225)
                start_x = 220 if ball_pos.x < 0 else -220
                predict_t = clamp(dist_to_ball / ball_speed / 200 + 0.5, 0.8, 2.0) if ball_speed > 5 else 1.2
                client.spawn_trap9(Vector2(start_x, ball_pos.y), Vector2(bx, by), predict_t)

        else:
            fence_active = False

        if speed > 100:
            if 2 in available:
                delay = clamp(0.5 + speed / 400, 0.8, 2.0)
                radius = clamp(60 + speed * 0.5, 80, 150)
                client.spawn_trap2(delay, radius)
            if 9 in available:
                pred_x = clamp(opp_pos.x + opp_vel.x * 1.0, -225, 225)
                pred_y = clamp(opp_pos.y + opp_vel.y * 1.0, -225, 225)
                start_x = 220 if opp_pos.x < 0 else -220
                client.spawn_trap9(Vector2(start_x, opp_pos.y), Vector2(pred_x, pred_y), 1.0)

        if 3 in available and dist_to_ball > 80:
            chase_dir = Vector2(ball_pos.x - opp_pos.x, ball_pos.y - opp_pos.y)
            mag = math.hypot(chase_dir.x, chase_dir.y)
            if mag > 0:
                chase_dir = Vector2(chase_dir.x / mag, chase_dir.y / mag)
            client.spawn_trap3(opp_pos, chase_dir, clamp(150 + speed * 0.5, 150, 300))

        if remaining <= previous_print_time - 2.0:
            print(f"Denier | Time: {remaining:.1f}s | HP: {my_health} | Energy: {my_energy}/{energy_cap}")
            print(f"Combo: {opp_combo} | Ball: {dist_to_ball:.0f} | Speed: {speed:.0f}")
            print("---")
            previous_print_time = remaining
'''
    },
    {
        "name": "Zone Control",
        "icon": "square.grid.3x3",
        "description": "Controls field with tsunami pushes, dance lines, and ripples.",
        "code": '''# ruff: disable[F403]
# ruff: disable[F405]
from api import *
import math
import random

MIN_COORDINATE = -220
MAX_COORDINATE = 220
PLAYER_RADIUS = 13.5
FIELD_SIZE = 440
MAX_HEALTH = 5
MAX_HEAL_COUNT = 2

HEAL_COST_BY_PHASE = {0: 25, 1: 35, 2: 45, 3: 52, 4: 60, 5: 65}
ENERGY_CAP_BY_PHASE = {0: 35, 1: 50, 2: 60, 3: 70, 4: 77, 5: 85}
ALL_DIRS = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def quadrant_of(pos):
    if pos.x >= 0 and pos.y >= 0:
        return 1
    if pos.x < 0 and pos.y >= 0:
        return 2
    if pos.x < 0 and pos.y < 0:
        return 3
    return 4


def run(client):
    client.print_api_errors = False
    heal_count = 0
    previous_print_time = 300.0
    last_push_time = 0.0
    trap_cycle = 0

    while True:
        remaining = 300.0 - client.get_elapsed_time()
        phase = client.get_phase()
        my_energy = client.get_my_energy()
        my_health = client.get_my_health()
        energy_cap = ENERGY_CAP_BY_PHASE.get(phase, 85)
        heal_cost = HEAL_COST_BY_PHASE.get(phase, 65)
        opp_pos = client.get_opponent_player_position()
        opp_vel = client.get_opponent_player_velocity()
        ball_pos = client.get_opponent_energy_ball_position()
        speed = math.hypot(opp_vel.x, opp_vel.y)
        available = client.get_available_traps()
        trap_cycle += 1

        if my_health <= 1 and heal_count < MAX_HEAL_COUNT and my_energy >= heal_cost:
            result = client.heal()
            if not isinstance(result, ApiError):
                heal_count += 1

        center_dist = distance(opp_pos, Vector2(0, 0))
        near_ball = distance(opp_pos, ball_pos) < 160
        q = quadrant_of(opp_pos)
        energy_high = my_energy >= energy_cap * 0.7

        if 8 in available and trap_cycle % 3 == 0 and center_dist < 180:
            if q in (1, 3):
                x_divider = random.uniform(-100 if q == 3 else 0, 0 if q == 3 else 100)
                client.spawn_trap8(Vector2(x_divider, -220), Vector2(x_divider + 15, 220))
            else:
                y_divider = random.uniform(-100 if q == 2 else 0, 0 if q == 2 else 100)
                client.spawn_trap8(Vector2(-220, y_divider), Vector2(220, y_divider + 15))

        if 4 in available and center_dist < 130 and remaining - last_push_time > 2.0:
            if abs(opp_pos.x) > abs(opp_pos.y):
                push_dir = Direction.RIGHT if opp_pos.x > 0 else Direction.LEFT
            else:
                push_dir = Direction.DOWN if opp_pos.y > 0 else Direction.UP
            client.spawn_trap4(Vector2(clamp(opp_pos.x, -100, 100), clamp(opp_pos.y, -100, 100)), push_dir)
            last_push_time = remaining

        if 5 in available:
            client.spawn_trap5(Vector2(clamp(ball_pos.x, -150, 150), clamp(ball_pos.y, -150, 150)))
            client.spawn_trap5(Vector2(clamp(opp_pos.x, -150, 150), clamp(opp_pos.y, -150, 150)))

        if 1 in available:
            predict_t = 0.25 + speed / 500
            px = clamp(opp_pos.x + opp_vel.x * predict_t, -225, 225)
            py = clamp(opp_pos.y + opp_vel.y * predict_t, -225, 225)
            client.spawn_trap1(Vector2(px, py))

        if energy_high:
            if 6 in available and 7 in available:
                sweep = Direction.UP if opp_pos.y > 0 else Direction.DOWN
                if center_dist < 60:
                    sweep = Direction.LEFT if opp_pos.x > 0 else Direction.RIGHT
                client.spawn_trap6(sweep, clamp(120 + center_dist * 0.5, 120, 220))
                cx = clamp(opp_pos.x, -400, 400)
                cy = clamp(opp_pos.y, -280, 280)
                client.spawn_trap7(Vector2(cx, cy), clamp(100 + center_dist * 0.4, 100, 200))
            elif 6 in available:
                sweep = Direction.LEFT if opp_pos.x > 0 else Direction.RIGHT
                if abs(opp_pos.y) > abs(opp_pos.x):
                    sweep = Direction.UP if opp_pos.y > 0 else Direction.DOWN
                client.spawn_trap6(sweep, 180.0)
            elif 7 in available:
                cx = clamp(opp_pos.x, -400, 400)
                cy = clamp(opp_pos.y, -280, 280)
                client.spawn_trap7(Vector2(cx, cy), 180.0)

        if 2 in available and speed > 40:
            delay = clamp(0.8 + speed / 500, 0.8, 2.0)
            radius = clamp(60 + speed * 0.6, 80, 150)
            client.spawn_trap2(delay, radius)

        if remaining <= previous_print_time - 2.0:
            print(f"Zone | Time: {remaining:.1f}s | Phase: {phase} | HP: {my_health} | Energy: {my_energy}/{energy_cap}")
            print(f"Opp: ({opp_pos.x:.0f}, {opp_pos.y:.0f}) | Quad: {q} | Center: {center_dist:.0f}")
            print("---")
            previous_print_time = remaining
'''
    },
    {
        "name": "Predictive Sniper",
        "icon": "target",
        "description": "Precision prediction with watermelon mortar (trap9) and tracking ring (trap2).",
        "code": '''# ruff: disable[F403]
# ruff: disable[F405]
from api import *
import math
import random

MIN_COORDINATE = -220
MAX_COORDINATE = 220
PLAYER_RADIUS = 13.5
FIELD_SIZE = 440
MAX_HEALTH = 5
MAX_HEAL_COUNT = 2

HEAL_COST_BY_PHASE = {0: 25, 1: 35, 2: 45, 3: 52, 4: 60, 5: 65}
ENERGY_CAP_BY_PHASE = {0: 35, 1: 50, 2: 60, 3: 70, 4: 77, 5: 85}
PHASE_LEAD = {0: 0.6, 1: 0.7, 2: 0.8, 3: 0.9, 4: 1.0, 5: 1.1}
ALL_DIRS = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def run(client):
    client.print_api_errors = False
    heal_count = 0
    previous_print_time = 300.0
    prev_opp_vel = Vector2(0, 0)
    dodge_pattern = []

    while True:
        remaining = 300.0 - client.get_elapsed_time()
        phase = client.get_phase()
        my_energy = client.get_my_energy()
        my_health = client.get_my_health()
        energy_cap = ENERGY_CAP_BY_PHASE.get(phase, 85)
        heal_cost = HEAL_COST_BY_PHASE.get(phase, 65)
        opp_pos = client.get_opponent_player_position()
        opp_vel = client.get_opponent_player_velocity()
        opp_combo = client.get_opponent_combo()
        ball_pos = client.get_opponent_energy_ball_position()
        speed = math.hypot(opp_vel.x, opp_vel.y)
        available = client.get_available_traps()
        lead = PHASE_LEAD.get(phase, 0.8)

        if speed > 30 and prev_opp_vel.x != 0:
            accel_x = opp_vel.x - prev_opp_vel.x
            accel_y = opp_vel.y - prev_opp_vel.y
            accel_mag = math.hypot(accel_x, accel_y)
            if accel_mag > 20:
                dodge_pattern.append((accel_x / accel_mag, accel_y / accel_mag))
                if len(dodge_pattern) > 4:
                    dodge_pattern.pop(0)
        prev_opp_vel = Vector2(opp_vel.x, opp_vel.y)

        x_axis_bias = sum(p[0] for p in dodge_pattern) / max(len(dodge_pattern), 1)
        y_axis_bias = sum(p[1] for p in dodge_pattern) / max(len(dodge_pattern), 1)
        dodge_bias = math.hypot(x_axis_bias, y_axis_bias)

        if my_health <= 1 and heal_count < MAX_HEAL_COUNT and my_energy >= heal_cost:
            result = client.heal()
            if not isinstance(result, ApiError):
                heal_count += 1

        if opp_combo >= 3 and 6 in available and 7 in available:
            client.spawn_trap6(random.choice(ALL_DIRS), 250.0)
            client.spawn_trap7(Vector2(clamp(opp_pos.x, -400, 400), clamp(opp_pos.y, -280, 280)), 200.0)
            continue

        if speed > 60:
            pred_x = clamp(opp_pos.x + opp_vel.x * lead, -225, 225)
            pred_y = clamp(opp_pos.y + opp_vel.y * lead, -225, 225)
            dist_to_pred = distance(opp_pos, Vector2(pred_x, pred_y))

            if dodge_bias > 0.3:
                dodge_x = clamp(pred_x + x_axis_bias * 40, -225, 225)
                dodge_y = clamp(pred_y + y_axis_bias * 40, -225, 225)
                if 9 in available:
                    start_x = 220 if opp_pos.x < 0 else -220
                    air_t = clamp(dist_to_pred / 160 + 0.4, 0.8, 2.5)
                    client.spawn_trap9(Vector2(start_x, opp_pos.y), Vector2(dodge_x, dodge_y), air_t)
                    client.spawn_trap9(Vector2(start_x, opp_pos.y), Vector2(pred_x, pred_y), air_t * 0.7)
                if 2 in available:
                    client.spawn_trap2(clamp(1.0 + speed / 400, 0.8, 2.0), clamp(80 + dist_to_pred * 0.5, 80, 150))
            else:
                if 9 in available:
                    start_x = 220 if opp_pos.x < 0 else -220
                    air_t = clamp(dist_to_pred / 150 + 0.3, 0.8, 2.5)
                    client.spawn_trap9(Vector2(start_x, opp_pos.y), Vector2(pred_x, pred_y), air_t)
                if 2 in available:
                    delay = clamp(0.6 + speed / 400, 0.8, 2.0)
                    radius = clamp(60 + speed * 0.5, 80, 150)
                    client.spawn_trap2(delay, radius)

            if 7 in available:
                cx = clamp(pred_x + x_axis_bias * 30, -400, 400)
                cy = clamp(pred_y + y_axis_bias * 30, -280, 280)
                rate = clamp(100 + dist_to_pred * 0.4, 100, 200)
                client.spawn_trap7(Vector2(cx, cy), rate)

            if 10 in available and speed > 130 and dodge_bias > 0.3:
                dx = 1.0 if opp_vel.x > 0 else -1.0
                spread_y = clamp(y_axis_bias * 0.8, -0.5, 0.5)
                client.spawn_trap10(
                    Vector2(clamp(opp_pos.x - dx * 30, -250, 250), clamp(opp_pos.y, -280, 280)),
                    Vector2(dx, -0.4 + spread_y), Vector2(dx, 0.0 + spread_y), Vector2(dx, 0.4 + spread_y),
                )

        elif speed < 50 and my_energy >= 15:
            if 3 in available:
                toward = Vector2(-opp_pos.x, -opp_pos.y)
                mag = math.hypot(toward.x, toward.y)
                if mag > 0:
                    toward = Vector2(toward.x / mag, toward.y / mag)
                client.spawn_trap3(opp_pos, toward, 300.0)
            if 1 in available:
                client.spawn_trap1(Vector2(clamp(ball_pos.x, -225, 225), clamp(ball_pos.y, -225, 225)))

        if remaining <= previous_print_time - 2.0:
            print(f"Sniper | Time: {remaining:.1f}s | HP: {my_health} | Energy: {my_energy}/{energy_cap}")
            print(f"Target: ({opp_pos.x:.0f}, {opp_pos.y:.0f}) | Speed: {speed:.0f} | Dodge: {dodge_bias:.2f}")
            print("---")
            previous_print_time = remaining
'''
    },
    {
        "name": "Spam Aggressor",
        "icon": "hand.raised",
        "description": "Constant cheap trap pressure with trap1 + trap5, overwhelm with volume.",
        "code": '''# ruff: disable[F403]
# ruff: disable[F405]
from api import *
import math
import random

MIN_COORDINATE = -220
MAX_COORDINATE = 220
PLAYER_RADIUS = 13.5
FIELD_SIZE = 440
MAX_HEALTH = 5
MAX_HEAL_COUNT = 2

HEAL_COST_BY_PHASE = {0: 25, 1: 35, 2: 45, 3: 52, 4: 60, 5: 65}
ENERGY_CAP_BY_PHASE = {0: 35, 1: 50, 2: 60, 3: 70, 4: 77, 5: 85}
ALL_DIRS = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]
TRAP1_OFFSETS = [(0, 0), (30, 30), (-30, -30), (30, -30), (-30, 30), (60, 0), (-60, 0), (0, 60), (0, -60)]


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def run(client):
    client.print_api_errors = False
    heal_count = 0
    previous_print_time = 300.0
    burst_idx = 0

    while True:
        remaining = 300.0 - client.get_elapsed_time()
        phase = client.get_phase()
        my_energy = client.get_my_energy()
        my_health = client.get_my_health()
        energy_cap = ENERGY_CAP_BY_PHASE.get(phase, 85)
        heal_cost = HEAL_COST_BY_PHASE.get(phase, 65)
        opp_pos = client.get_opponent_player_position()
        opp_vel = client.get_opponent_player_velocity()
        ball_pos = client.get_opponent_energy_ball_position()
        speed = math.hypot(opp_vel.x, opp_vel.y)
        available = client.get_available_traps()

        if my_health <= 2 and heal_count < MAX_HEAL_COUNT and my_energy >= heal_cost:
            result = client.heal()
            if not isinstance(result, ApiError):
                heal_count += 1

        if 5 in available:
            grid5 = [(0, 0), (40, 40), (-40, -40), (40, -40), (-40, 40), (80, 0), (-80, 0)]
            for dx, dy in grid5:
                sx = clamp(opp_pos.x + dx, -150, 150)
                sy = clamp(opp_pos.y + dy, -150, 150)
                client.spawn_trap5(Vector2(sx, sy))

        if 1 in available:
            burst_idx = (burst_idx + 1) % len(TRAP1_OFFSETS)
            offset = TRAP1_OFFSETS[burst_idx]
            nx = clamp(opp_pos.x + opp_vel.x * 0.2 + offset[0], -225, 225)
            ny = clamp(opp_pos.y + opp_vel.y * 0.2 + offset[1], -225, 225)
            client.spawn_trap1(Vector2(nx, ny))
            if my_energy >= 12:
                nx2 = clamp(opp_pos.x + opp_vel.x * 0.2 - offset[0], -225, 225)
                ny2 = clamp(opp_pos.y + opp_vel.y * 0.2 - offset[1], -225, 225)
                client.spawn_trap1(Vector2(nx2, ny2))

        if 6 in available and my_energy >= energy_cap * 0.4:
            client.spawn_trap6(random.choice(ALL_DIRS), random.uniform(200.0, 250.0))

        if 7 in available and my_energy >= energy_cap * 0.4:
            cx = clamp(opp_pos.x, -400, 400)
            cy = clamp(opp_pos.y, -280, 280)
            client.spawn_trap7(Vector2(cx, cy), random.uniform(180.0, 220.0))

        if distance(opp_pos, ball_pos) < 250:
            if 9 in available:
                bx = clamp(ball_pos.x, -225, 225)
                by = clamp(ball_pos.y, -225, 225)
                start_x = 220 if ball_pos.x < 0 else -220
                client.spawn_trap9(Vector2(start_x, ball_pos.y), Vector2(bx, by), 0.8)
            if 3 in available:
                toward = Vector2(-opp_pos.x, -opp_pos.y)
                mag = math.hypot(toward.x, toward.y)
                if mag > 0:
                    toward = Vector2(toward.x / mag, toward.y / mag)
                client.spawn_trap3(Vector2(clamp(opp_pos.x, -220, 220), clamp(opp_pos.y, -220, 220)), toward, 300.0)

        if speed > 150 and 2 in available:
            client.spawn_trap2(1.0, 100.0)

        if remaining <= previous_print_time - 2.0:
            print(f"Spam | Time: {remaining:.1f}s | HP: {my_health} | Energy: {my_energy}/{energy_cap}")
            print("---")
            previous_print_time = remaining
'''
    },
    {
        "name": "Sky Net",
        "icon": "cloud",
        "description": "Air control: forces jumps with dance line (trap6) + ripple (trap7) combos.",
        "code": '''# ruff: disable[F403]
# ruff: disable[F405]
from api import *
import math
import random

MIN_COORDINATE = -220
MAX_COORDINATE = 220
PLAYER_RADIUS = 13.5
FIELD_SIZE = 440
MAX_HEALTH = 5
MAX_HEAL_COUNT = 2

HEAL_COST_BY_PHASE = {0: 25, 1: 35, 2: 45, 3: 52, 4: 60, 5: 65}
ENERGY_CAP_BY_PHASE = {0: 35, 1: 50, 2: 60, 3: 70, 4: 77, 5: 85}
ALL_DIRS = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def run(client):
    client.print_api_errors = False
    heal_count = 0
    previous_print_time = 300.0
    combo_chain = 0
    last_combo_time = 0.0

    while True:
        remaining = 300.0 - client.get_elapsed_time()
        phase = client.get_phase()
        my_energy = client.get_my_energy()
        my_health = client.get_my_health()
        energy_cap = ENERGY_CAP_BY_PHASE.get(phase, 85)
        heal_cost = HEAL_COST_BY_PHASE.get(phase, 65)
        opp_pos = client.get_opponent_player_position()
        opp_vel = client.get_opponent_player_velocity()
        opp_combo = client.get_opponent_combo()
        ball_pos = client.get_opponent_energy_ball_position()
        speed = math.hypot(opp_vel.x, opp_vel.y)
        available = client.get_available_traps()
        near_edge = abs(opp_pos.x) > 170 or abs(opp_pos.y) > 170

        if my_health <= 1 and heal_count < MAX_HEAL_COUNT and my_energy >= heal_cost:
            result = client.heal()
            if not isinstance(result, ApiError):
                heal_count += 1

        if remaining - last_combo_time < 1.5:
            combo_chain += 1
        else:
            combo_chain = 0
        last_combo_time = remaining

        if my_health > 2:
            if my_energy >= energy_cap * 0.45:
                if 6 in available and 7 in available:
                    if abs(opp_pos.x) > abs(opp_pos.y):
                        sweep = Direction.UP if opp_pos.y > 5 else Direction.DOWN
                    else:
                        sweep = Direction.LEFT if opp_pos.x > 5 else Direction.RIGHT
                    speed_val = clamp(150 + speed * 0.3 + combo_chain * 10, 150, 250)
                    client.spawn_trap6(sweep, speed_val)
                    cx = clamp(opp_pos.x, -400, 400)
                    cy = clamp(opp_pos.y, -280, 280)
                    rate = clamp(120 + combo_chain * 15, 120, 250)
                    client.spawn_trap7(Vector2(cx, cy), rate)
                    if combo_chain % 3 == 0 and 8 in available:
                        if abs(opp_pos.x) > 100:
                            client.spawn_trap8(Vector2(-220, opp_pos.y - 50), Vector2(220, opp_pos.y + 50))
                        else:
                            client.spawn_trap8(Vector2(opp_pos.x - 50, -220), Vector2(opp_pos.x + 50, 220))
                elif 6 in available:
                    sweep = Direction.LEFT if opp_pos.x > 0 else Direction.RIGHT
                    if abs(opp_pos.y) > abs(opp_pos.x):
                        sweep = Direction.UP if opp_pos.y > 0 else Direction.DOWN
                    client.spawn_trap6(sweep, clamp(180 + combo_chain * 5, 180, 250))

                elif 7 in available:
                    cx = clamp(opp_pos.x, -400, 400)
                    cy = clamp(opp_pos.y, -280, 280)
                    client.spawn_trap7(Vector2(cx, cy), clamp(150 + combo_chain * 10, 150, 250))

            if my_energy >= energy_cap * 0.25:
                if 2 in available:
                    delay = clamp(1.2 + combo_chain * 0.1, 1.0, 2.0)
                    radius = clamp(100 + combo_chain * 5, 100, 160)
                    client.spawn_trap2(delay, radius)
                if 9 in available:
                    pred_x = clamp(opp_pos.x + opp_vel.x * clamp(0.5 + combo_chain * 0.05, 0.5, 1.0), -225, 225)
                    pred_y = clamp(opp_pos.y + opp_vel.y * clamp(0.5 + combo_chain * 0.05, 0.5, 1.0), -225, 225)
                    start_x = 220 if opp_pos.x < 0 else -220
                    air_t = clamp(distance(opp_pos, Vector2(pred_x, pred_y)) / 160 + 0.3, 0.8, 2.5)
                    client.spawn_trap9(Vector2(start_x, opp_pos.y), Vector2(pred_x, pred_y), air_t)

        if 1 in available and my_energy >= 5:
            near_ball = Vector2(clamp(ball_pos.x, -225, 225), clamp(ball_pos.y, -225, 225))
            client.spawn_trap1(near_ball)
            if distance(opp_pos, ball_pos) < 200:
                near_opp = Vector2(clamp(opp_pos.x, -225, 225), clamp(opp_pos.y, -225, 225))
                client.spawn_trap1(near_opp)

        if remaining <= previous_print_time - 2.0:
            print(f"Sky Net | Time: {remaining:.1f}s | Phase: {phase} | HP: {my_health} | Energy: {my_energy}/{energy_cap}")
            print(f"Chain: {combo_chain} | Speed: {speed:.0f}")
            print("---")
            previous_print_time = remaining
'''
    },
    {
        "name": "Chaos Theory",
        "icon": "dice",
        "description": "Unpredictable random trap placement with smart energy management.",
        "code": '''# ruff: disable[F403]
# ruff: disable[F405]
from api import *
import math
import random

MIN_COORDINATE = -220
MAX_COORDINATE = 220
PLAYER_RADIUS = 13.5
FIELD_SIZE = 440
MAX_HEALTH = 5
MAX_HEAL_COUNT = 2

HEAL_COST_BY_PHASE = {0: 25, 1: 35, 2: 45, 3: 52, 4: 60, 5: 65}
ENERGY_CAP_BY_PHASE = {0: 35, 1: 50, 2: 60, 3: 70, 4: 77, 5: 85}
TRAP_COST = {1: 5, 2: 15, 3: 13, 4: 20, 5: 5, 6: 20, 7: 20, 8: 15, 9: 12, 10: 15}
ALL_DIRS = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]
LONG_RANGE = {9, 7, 2, 10}
SHORT_RANGE = {1, 4, 5, 8}


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def weighted_choice(traps, weights):
    if not traps:
        return None
    total = sum(weights.get(t, 1) for t in traps)
    r = random.uniform(0, total)
    running = 0.0
    for t in traps:
        running += weights.get(t, 1)
        if r <= running:
            return t
    return traps[-1]


def run(client):
    client.print_api_errors = False
    heal_count = 0
    previous_print_time = 300.0
    last_trap_id = 0
    same_trap_streak = 0
    mood = "neutral"

    while True:
        remaining = 300.0 - client.get_elapsed_time()
        phase = client.get_phase()
        my_energy = client.get_my_energy()
        my_health = client.get_my_health()
        energy_cap = ENERGY_CAP_BY_PHASE.get(phase, 85)
        heal_cost = HEAL_COST_BY_PHASE.get(phase, 65)
        opp_pos = client.get_opponent_player_position()
        opp_vel = client.get_opponent_player_velocity()
        ball_pos = client.get_opponent_energy_ball_position()
        speed = math.hypot(opp_vel.x, opp_vel.y)
        available = client.get_available_traps()

        if my_health <= 1 and heal_count < MAX_HEAL_COUNT and my_energy >= heal_cost:
            result = client.heal()
            if not isinstance(result, ApiError):
                heal_count += 1

        affordable = [t for t in available if my_energy >= TRAP_COST.get(t, 99)]
        if not affordable:
            continue

        dist_to_opp = distance(opp_pos, Vector2(0, 0))
        energy_pct = my_energy / max(energy_cap, 1)

        if energy_pct > 0.7:
            mood = "aggressive"
        elif energy_pct < 0.3 or my_health <= 2:
            mood = "defensive"
        else:
            mood = "neutral"

        weights = {t: 1.0 for t in affordable}
        if mood == "aggressive":
            for t in affordable:
                if t in (6, 7, 4, 9):
                    weights[t] = 2.0
                if t == last_trap_id:
                    weights[t] = 0.3
            if speed > 100:
                weights[9] = weights.get(9, 1) * 2.0
                weights[2] = weights.get(2, 1) * 1.5
        elif mood == "defensive":
            for t in affordable:
                if t in (1, 5, 8):
                    weights[t] = 2.5
                if t in (6, 7, 4):
                    weights[t] = 0.5
        else:
            if dist_to_opp < 80:
                for t in affordable:
                    if t in SHORT_RANGE:
                        weights[t] = 1.8
            elif dist_to_opp > 150:
                for t in affordable:
                    if t in LONG_RANGE:
                        weights[t] = 2.0
            if last_trap_id in affordable:
                weights[last_trap_id] = max(0.2, weights.get(last_trap_id, 1) - 0.5)

        pick = weighted_choice(affordable, weights)
        if pick is None:
            pick = random.choice(affordable)

        if pick == last_trap_id:
            same_trap_streak += 1
        else:
            same_trap_streak = 0
        last_trap_id = pick

        chaos_val = random.random()

        if pick == 1:
            target = ball_pos if chaos_val < 0.4 else opp_pos
            tx = clamp(target.x + random.uniform(-40, 40), -225, 225)
            ty = clamp(target.y + random.uniform(-40, 40), -225, 225)
            client.spawn_trap1(Vector2(tx, ty))
        elif pick == 2:
            delay = random.uniform(0.8, 2.0)
            radius = random.uniform(80, 150)
            client.spawn_trap2(delay, radius)
        elif pick == 3:
            toward = Vector2(-opp_pos.x, -opp_pos.y)
            mag = math.hypot(toward.x, toward.y)
            if mag > 0:
                toward = Vector2(toward.x / mag, toward.y / mag)
            client.spawn_trap3(Vector2(clamp(opp_pos.x, -220, 220), clamp(opp_pos.y, -220, 220)), toward, random.uniform(150, 300))
        elif pick == 4:
            push = random.choice([Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT])
            if abs(opp_pos.x) > 80:
                push = Direction.RIGHT if opp_pos.x > 0 else Direction.LEFT
            elif abs(opp_pos.y) > 80:
                push = Direction.DOWN if opp_pos.y > 0 else Direction.UP
            client.spawn_trap4(Vector2(clamp(opp_pos.x, -100, 100), clamp(opp_pos.y, -100, 100)), push)
        elif pick == 5:
            target = ball_pos if chaos_val < 0.6 else opp_pos
            sx = clamp(target.x + random.uniform(-30, 30), -150, 150)
            sy = clamp(target.y + random.uniform(-30, 30), -150, 150)
            client.spawn_trap5(Vector2(sx, sy))
            if my_energy >= TRAP_COST[5] * 2:
                sx2 = clamp(target.x + random.uniform(-30, 30), -150, 150)
                sy2 = clamp(target.y + random.uniform(-30, 30), -150, 150)
                client.spawn_trap5(Vector2(sx2, sy2))
        elif pick == 6:
            sweep = random.choice(ALL_DIRS)
            client.spawn_trap6(sweep, random.uniform(120, 250))
        elif pick == 7:
            cx = clamp(opp_pos.x, -400, 400)
            cy = clamp(opp_pos.y, -280, 280)
            client.spawn_trap7(Vector2(cx, cy), random.uniform(100, 220))
        elif pick == 8:
            if abs(opp_pos.x) < abs(opp_pos.y):
                y0 = clamp(opp_pos.y + random.uniform(-100, 100), -200, 200)
                client.spawn_trap8(Vector2(-220, y0 - 20), Vector2(220, y0 + 20))
            else:
                x0 = clamp(opp_pos.x + random.uniform(-100, 100), -200, 200)
                client.spawn_trap8(Vector2(x0 - 20, -220), Vector2(x0 + 20, 220))
        elif pick == 9:
            pred_x = clamp(opp_pos.x + opp_vel.x * random.uniform(0.3, 0.9), -225, 225)
            pred_y = clamp(opp_pos.y + opp_vel.y * random.uniform(0.3, 0.9), -225, 225)
            dist = distance(opp_pos, Vector2(pred_x, pred_y))
            air = clamp(dist / 150 + 0.3, 0.8, 2.5)
            start_x = 220 if opp_pos.x < 0 else -220
            client.spawn_trap9(Vector2(start_x, opp_pos.y), Vector2(pred_x, pred_y), air)
        elif pick == 10:
            dx = random.choice([-1.0, 1.0])
            spread = random.uniform(-0.5, 0.5)
            client.spawn_trap10(
                Vector2(clamp(opp_pos.x - dx * 30, -250, 250), clamp(opp_pos.y, -280, 280)),
                Vector2(dx, -0.4 + spread), Vector2(dx, 0.0 + spread), Vector2(dx, 0.4 + spread),
            )

        if remaining <= previous_print_time - 2.0:
            mood_str = ("A" if mood == "aggressive" else "D" if mood == "defensive" else "N")
            print(f"Chaos | Time: {remaining:.1f}s | HP: {my_health} | Energy: {my_energy}/{energy_cap}")
            print(f"Trap: {pick} [{mood_str}] | Available: {len(affordable)} | Streak: {same_trap_streak}")
            print("---")
            previous_print_time = remaining
'''
    },
]
