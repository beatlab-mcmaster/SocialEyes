import atexit
import cProfile
import io
import pstats

print("Profiling...")
pr = cProfile.Profile()
pr.enable()


def exit():
    pr.disable()
    print("Profiling completed")
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats()
    print(s.getvalue())


atexit.register(exit)
