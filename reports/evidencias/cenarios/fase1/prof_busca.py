import sys, os, random, time, cProfile, pstats, tempfile
sys.path.insert(0, "/home/claude/friday-pi/tests")
import bench_busca as BB
import _ambiente as E, memoria as M
os.environ["OBSIDIAN_VAULT"] = tempfile.mkdtemp(prefix="cofre-prof-", dir=E.TMP)
M._cache.clear()
BB.popular(20000, random.Random(7))
for i in range(4):
    t = time.perf_counter(); M.buscar("palavra0001 palavra0002", 5); print(f"busca {i}: {(time.perf_counter()-t)*1000:.0f} ms  cache={len(M._cache)} max={M._cache_max()}")
pr = cProfile.Profile(); pr.enable(); M.buscar("palavra0001 palavra0002", 5); pr.disable()
pstats.Stats(pr).sort_stats("cumulative").print_stats(12)
