"""Select a frozen acquisition segment without bridging a recording pause."""


def segment_bounds(sample_count, sampling_hz, segment_starts, decision=None):
    starts = list(segment_starts)
    if starts and (
        starts[0] != 0
        or any(b <= a for a, b in zip(starts, starts[1:]))
        or starts[-1] >= sample_count
    ):
        raise ValueError("invalid_ACQ_segment_boundaries")
    if decision is None:
        if len(starts) > 1:
            raise ValueError("multiple_ACQ_segments_require_frozen_choice")
        return 0, sample_count
    if sampling_hz != decision["sampling_hz"]:
        raise ValueError("segment_sampling_rate_changed")
    i = decision["segment_index"]
    if not 0 <= i < len(starts) or len(starts) != decision["segment_count"]:
        raise ValueError("segment_count_changed")
    a = starts[i]
    b = starts[i + 1] if i + 1 < len(starts) else sample_count
    if a != decision["start_sample"] or b != decision["end_sample"]:
        raise ValueError("segment_bounds_changed")
    return a, b
