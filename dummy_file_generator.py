# generate_dummy_file.py

def generate_dummy_file(filename, size_in_mb=5):
    line = "This is a dummy line for testing chunk-based reading. part 22222222 II\n"
    line_bytes = len(line.encode('utf-8'))

    total_lines = (size_in_mb * 1024 * 1024) // line_bytes

    with open(filename, 'w') as f:
        for _ in range(total_lines):
            f.write(line)

if __name__ == "__main__":
    generate_dummy_file("myfile2.txt")
