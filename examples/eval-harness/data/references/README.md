# references/ — ground truth

    gold/     human-authored. The thing you actually want to be right about.
    silver/   model-generated. Cheap, plentiful, and not the same thing.

**They are not interchangeable.** A run scored against a mix of the two is
reporting a number nobody can interpret. If you use silver because gold is
expensive, say so wherever the number is published.
