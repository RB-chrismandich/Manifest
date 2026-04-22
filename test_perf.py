import time
from collections import Counter

def original():
    start = time.time()
    for _ in range(100):
        outputs = ["This is a test output with some significant words like application, performance, optimization, bottleneck" * 50] * 3

        all_words = set()
        word_counts = {}

        for output in outputs:
            words = set(word.lower() for word in output.split() if len(word) > 4)
            all_words.update(words)
            for word in words:
                word_counts[word] = word_counts.get(word, 0) + 1

        if not all_words:
            consensus_score = 0
        else:
            common_words = sum(1 for count in word_counts.values() if count > 1)
            consensus_score = int((common_words / len(all_words)) * 100)
    return time.time() - start

def optimized():
    start = time.time()
    for _ in range(100):
        outputs = ["This is a test output with some significant words like application, performance, optimization, bottleneck" * 50] * 3

        if len(outputs) < 2:
            consensus_score = 0
        else:
            word_sets = [set(word.lower() for word in output.split() if len(word) > 4) for output in outputs]

            if not word_sets:
                consensus_score = 0
            else:
                all_words = set().union(*word_sets)
                if not all_words:
                    consensus_score = 0
                else:
                    counts = Counter()
                    for s in word_sets:
                        counts.update(s)

                    common_words = sum(1 for count in counts.values() if count > 1)
                    consensus_score = int((common_words / len(all_words)) * 100)
    return time.time() - start

orig_t = original()
opt_t = optimized()
print(f"Original: {orig_t:.5f}s")
print(f"Optimized: {opt_t:.5f}s")
print(f"Improvement: {(orig_t - opt_t)/orig_t*100:.2f}%")
