def split_blocks(lines):
    block = []
    for line in lines:
        if line.strip() == "":
            if block:
                yield block
                block = []
        else:
            block.append(line)
    if block:
        yield block
