import timeit

def consensus_original(outputs):
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
    return consensus_score

def consensus_optimized(outputs):
    from collections import Counter
    if len(outputs) < 2: return 0

    # Process the first output to initialize our sets/counts
    # This avoids adding to all_words words that only appear in one output
    # if we only care about words appearing in multiple
    # Wait, the original calculates % of common words over ALL unique words across ALL outputs.

    # Let's optimize the loop
    word_sets = [set(word.lower() for word in output.split() if len(word) > 4) for output in outputs]

    if not word_sets:
        return 0

    all_words = set().union(*word_sets)
    if not all_words:
        return 0

    # Count occurrences across sets
    counts = Counter()
    for s in word_sets:
        counts.update(s)

    common_words = sum(1 for count in counts.values() if count > 1)
    return int((common_words / len(all_words)) * 100)

output1 = "This is a test output with some significant words like application, performance, optimization, bottleneck" * 50
output2 = "Another test output featuring application, performance, improvement, completely, different, words" * 50
output3 = "Final test output with application, performance, bottleneck, totally, random, content" * 50
outputs = [output1, output2, output3]

print(f"Original score: {consensus_original(outputs)}")
print(f"Optimized score: {consensus_optimized(outputs)}")

try:
    orig_time = timeit.timeit("consensus_original(outputs)", globals=globals(), number=1000)
    opt_time = timeit.timeit("consensus_optimized(outputs)", globals=globals(), number=1000)

    print(f"Original time: {orig_time:.4f}s")
    print(f"Optimized time: {opt_time:.4f}s")
    print(f"Improvement: {(orig_time - opt_time) / orig_time * 100:.2f}%")
except Exception as e:
    import traceback
    traceback.print_exc()
