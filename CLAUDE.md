# Project Requirements & Standing Rules

## traveldestinations.json — MANDATORY FORMAT RULE

**NEVER use `json.dump(..., indent=2)` or any full pretty-print when writing back to `traveldestinations.json`.**

The file must stay **under 2,500 lines** (target ~2,000). Using standard `indent=2` expands it to 50,000+ lines and wastes significant token usage to fix.

### Required write format

Always use this exact serializer pattern:

```python
import json

def write_destinations(data, path='traveldestinations.json'):
    def compact(val):
        return json.dumps(val, ensure_ascii=False, separators=(',', ':'))

    lines = ['{']
    top_keys = list(data.keys())
    for ti, top_key in enumerate(top_keys):
        top_val = data[top_key]
        top_comma = ',' if ti < len(top_keys) - 1 else ''
        is_city = isinstance(top_val, dict) and any(
            k in top_val for k in ('name', 'hotels', 'iata', 'baseFare')
        )
        if not is_city:
            lines.append(f'  {json.dumps(top_key)}: {compact(top_val)}{top_comma}')
        else:
            inner_keys = list(top_val.keys())
            lines.append(f'  {json.dumps(top_key)}: {{')
            for ii, ik in enumerate(inner_keys):
                inner_comma = ',' if ii < len(inner_keys) - 1 else ''
                lines.append(f'    {json.dumps(ik)}: {compact(top_val[ik])}{inner_comma}')
            lines.append(f'  }}{top_comma}')
    lines.append('}')

    output = '\n'.join(lines) + '\n'
    with open(path, 'w') as f:
        f.write(output)

    line_count = output.count('\n')
    if line_count > 2500:
        raise RuntimeError(f"traveldestinations.json is {line_count} lines — exceeds 2,500 line limit. Do not commit.")
    return line_count
```

### Format rules
- **Meta keys** (`destinationLinks`, `mappings`, `specialEvents`, etc.) → single compact line
- **City destination objects** → one property per line (2-level expand only)
- **Arrays and nested objects** within city properties → minified on one line

### After every write
Always verify line count before committing:
```python
line_count = output.count('\n')
print(f"Line count: {line_count}")  # Must be < 2500
```

If over 2,500 lines — **stop, do not commit, fix the serializer first**.
