"""
Sorting tools
"""


def __partition(array: list, low: int, high: int, value_getter: callable):
    """
    Last value is selected as pivot value (for simplicity).
    Moves values lower than the pivot value to be before.
    Moves values greater than the pivot value to be after.
    `value_getter` allows access to nested values in the array elements.
    """
    # last value is always the pivot value
    pivot_value = value_getter(array[high])
    pivot_index = low - 1

    # iterate through elements
    for i in range(low, high):

        if value_getter(array[i]) < pivot_value:
            pivot_index += 1
            __swap(array, pivot_index, i)

    pivot_index += 1
    __swap(array, pivot_index, high)
    return pivot_index


def __swap(array: list, index1: int, index2: int) -> None:
    """
    Array must be mutable to swap values at indices.
    """
    array[index1], array[index2] = array[index2], array[index1]


def quicksort(array: list, low: int, high: int, value_getter: callable):
    """
    Get pivot index which sorts everything before and after to be less
    and greater than the pivot value respectively. Call this recursively
    on the partions below and above the pivot index.
    `value_getter` allows access to nested values in the array elements.
    """
    if low < high:
        pivot_index = __partition(array, low, high, value_getter)
        # sort bottom half
        quicksort(array, low, pivot_index - 1, value_getter)
        # sort top half
        quicksort(array, pivot_index + 1, high, value_getter)
