def assign_numbers(captions):
    numbers = {}
    counter = 0
    for key in captions:
        counter += 1
        numbers[key] = counter
    return numbers
