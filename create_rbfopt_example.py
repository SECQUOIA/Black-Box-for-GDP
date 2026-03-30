# This script creates a visual example of derivative-free optimization (DFO) in an integer lattice, using a simple objective function and a predefined trajectory of samples. 
# The resulting animation illustrates the optimization process, showing the sampled points, the incumbent solution, and the optimal point in the lattice.
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

# Masks
feasible_mask = [ (17, 1), (17, 2), (17, 3), (17, 4), (17, 5), (17, 6), (17, 7), (17, 8), (17, 9), (17, 10), (17, 11), (17, 12), (17, 13), (17, 14), (17, 15), (17, 16), (17, 17),
                  (16, 1), (16, 2), (16, 3), (16, 4), (16, 5), (16, 6), (16, 7), (16, 8), (16, 9), (16, 10), (16, 11), (16, 12), (16, 13), (16, 14), (16, 15), (16, 16),
                  (15, 1), (15, 2), (15, 3), (15, 4), (15, 5), (15, 6), (15, 7), (15, 8), (15, 9), (15, 10), (15, 11), (15, 12), (15, 13), (15, 14), (15, 15),
                  (14, 1), (14, 2), (14, 3), (14, 4), (14, 5), (14, 6), (14, 7), (14, 8), (14, 9), (14, 10), (14, 11), (14, 12), (14, 13), (14, 14),
                  (13, 1), (13, 2), (13, 3), (13, 4), (13, 5), (13, 6), (13, 7), (13, 8), (13, 9), (13, 10), (13, 11), (13, 12), (13, 13),
                  (12, 1), (12, 2), (12, 3), (12, 4), (12, 5), (12, 6), (12, 7), (12, 8), (12, 9), (12, 10), (12, 11), (12, 12),
                  (11, 1), (11, 2), (11, 3), (11, 4), (11, 5), (11, 6), (11, 7), (11, 8), (11, 9), (11, 10), (11, 11),
                  (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7), (10, 8), (10, 9), (10, 10),
                  (9, 1), (9, 2), (9, 3), (9, 4), (9, 5), (9, 6), (9, 7), (9, 8), (9, 9),
                  (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 6), (8, 7),(8, 8),
                  (7, 1), (7, 2), (7, 3), (7, 4), (7, 5), (7, 6), (7, 7),
                  (6, 1), (6, 2), (6, 3), (6, 4), (6, 5), (6, 6),
                  (5, 1), (5, 2), (5, 3), (5, 4), (5, 5),
                  (4, 1), (4, 2), (4, 3), (4, 4),
                  (3, 1), (3, 2), (3, 3),
                  (2, 1), (2, 2),
                  (1, 1)
]
infeasible_mask = [(1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8), (1, 9), (1, 10), (1, 11), (1, 12), (1, 13), (1, 14), (1, 15), (1, 16), (1, 17),
    (2, 3), (2, 4), (2, 5), (2, 6), (2, 7), (2, 8), (2, 9), (2, 10), (2, 11), (2, 12), (2, 13), (2, 14), (2, 15), (2, 16), (2, 17),
    (3, 4), (3, 5), (3, 6), (3, 7), (3, 8), (3, 9), (3, 10), (3, 11), (3, 12), (3, 13), (3, 14), (3, 15), (3, 16), (3, 17),
    (4, 5), (4, 6), (4, 7), (4, 8), (4, 9), (4, 10), (4, 11), (4, 12), (4, 13), (4, 14), (4, 15), (4, 16), (4, 17),
    (5, 6), (5, 7), (5, 8), (5, 9), (5, 10), (5, 11), (5, 12), (5, 13), (5, 14), (5, 15), (5, 16), (5, 17),
    (6, 7), (6, 8), (6, 9), (6, 10), (6, 11), (6, 12), (6, 13), (6, 14), (6, 15), (6, 16), (6, 17),
    (7, 8), (7, 9), (7, 10), (7, 11), (7, 12), (7, 13), (7, 14), (7, 15), (7, 16), (7, 17),
    (8, 9), (8, 10), (8, 11), (8, 12), (8, 13), (8, 14), (8, 15), (8, 16), (8, 17),
    (9, 10), (9, 11), (9, 12), (9, 13), (9, 14), (9, 15), (9, 16), (9, 17),
    (10, 11), (10, 12), (10, 13), (10, 14), (10, 15), (10, 16), (10, 17),
    (11, 12), (11, 13), (11, 14), (11, 15), (11, 16), (11, 17),
    (12, 13), (12, 14), (12, 15), (12, 16), (12, 17),
    (13, 14), (13, 15), (13, 16), (13, 17),
    (14, 15), (14, 16), (14, 17),
    (15, 16), (15, 17),
    (16, 17)
]

# Sampling
rng = np.random.default_rng(7)
feasible_set = list(set(feasible_mask) - {(17, 17)})
rng.shuffle(feasible_set)
num_random_samples = 15
random_samples = feasible_set[:num_random_samples]
trajectory = random_samples + [(17, 17)]

def objective(x, y):
    return -((x - 17)**2 + (y - 17)**2)

obj_values = [objective(x, y) for (x, y) in trajectory]

# Plot
fig, ax = plt.subplots(figsize=(6.8, 6.8))
ax.set_aspect('equal', 'box')
ax.set_xlim(0.5, 17.5)
ax.set_ylim(0.5, 17.5)
ax.set_xticks(range(1, 18))
ax.set_yticks(range(1, 18))
ax.grid(True, linestyle=':', linewidth=0.7)
ax.set_xlabel(r'$Z_{E1}$, Number of Reactors', fontsize=14)
ax.set_ylabel(r'$Z_{E2}$, Position of the Reflux', fontsize=14)
ax.set_title('Derivitive-Free Optimization in Integer Lattice', fontsize=16)

# Masks
if feasible_mask:
    fx, fy = zip(*feasible_mask)
    ax.scatter(fx, fy, s=50, marker='o', alpha=0.25, label='Feasible points (mask)')
if infeasible_mask:
    ix, iy = zip(*infeasible_mask)
    ax.scatter(ix, iy, s=50, marker='x', alpha=0.6, label='Infeasible points (mask)')
ax.legend(loc='lower right', fontsize=10)

# Artists
sample_scatter = ax.scatter([], [], s=60, marker='s')
best_scatter = ax.scatter([], [], s=120, marker='*')
arrow_artists = []
text_iter = ax.text(0.02, 0.98, '', transform=ax.transAxes, va='top', fontsize=12)
text_best = ax.text(0.02, 0.92, '', transform=ax.transAxes, va='top', fontsize=12)

sampled_x, sampled_y = [], []
best_x, best_y, best_val = None, None, -np.inf

def init():
    sample_scatter.set_offsets(np.empty((0, 2)))
    best_scatter.set_offsets(np.empty((0, 2)))
    text_iter.set_text('')
    text_best.set_text('')
    for art in arrow_artists:
        art.remove()
    arrow_artists.clear()
    return [sample_scatter, best_scatter, text_iter, text_best]

def update(frame):
    global best_x, best_y, best_val
    x, y = trajectory[frame]
    val = obj_values[frame]

    sampled_x.append(x)
    sampled_y.append(y)
    sample_scatter.set_offsets(np.column_stack([sampled_x, sampled_y]))

    if frame > 0:
        x_prev, y_prev = trajectory[frame-1]
        arrow = ax.annotate('', xy=(x, y), xytext=(x_prev, y_prev),
                            arrowprops=dict(arrowstyle='->', lw=1.5))
        arrow_artists.append(arrow)

    if val > best_val:
        best_val = val
        best_x, best_y = x, y
    best_scatter.set_offsets(np.column_stack([[best_x], [best_y]]))

    text_iter.set_text(f'Iteration: {frame+1}')
    text_best.set_text(f'Incumbent at ({best_x:.0f}, {best_y:.0f})')

    if frame == len(trajectory) - 1:
        ax.scatter([17], [17], s=200, marker='o', facecolors='none', linewidths=2)
        ax.annotate('Optimum', xy=(17, 17), xytext=(16.2, 17.3))

    return [sample_scatter, best_scatter, text_iter, text_best] + arrow_artists

anim = FuncAnimation(fig, update, frames=len(trajectory), init_func=init,
                     interval=600, blit=False, repeat=False, save_count=len(trajectory))

out_path = 'gif/dfo_integer_lattice.gif'
anim.save(out_path, writer=PillowWriter(fps=2))

out_path
