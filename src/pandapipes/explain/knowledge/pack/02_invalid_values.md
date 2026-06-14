# Invalid Values and NaN

## Keywords
invalid, nan, none, negative, index, dtype, type, value, zero, infinite, inf, missing, undefined, diameter, length, mdot, pressure, KeyError, ValueError

## What it means
One or more network elements have parameters that violate pandapipes' type or range
constraints. NaN values propagate through the Jacobian and the solver diverges immediately,
often surfacing as `PipeflowNotConverged` or a NumPy "invalid value" warning.

## Cause 1: NaN in mdot_kg_per_s (sink / source)
A sink or source with an unset mass flow injects NaN into the mass balance.
```python
# Find NaN sinks:
print(net.sink[net.sink['mdot_kg_per_s'].isna()])

# Fix: fill with a numeric value or remove the element
net.sink['mdot_kg_per_s'] = net.sink['mdot_kg_per_s'].fillna(0.0)
```

## Cause 2: Non-positive pipe diameter or length
`inner_diameter_mm` and `length_km` must be strictly positive. A zero diameter is a
closed pipe (infinite resistance); a zero length makes the friction term singular.
```python
print(net.pipe[(net.pipe.inner_diameter_mm <= 0) | (net.pipe.length_km <= 0)])
# Fix:
net.pipe.at[bad_idx, 'inner_diameter_mm'] = 200.0   # mm
net.pipe.at[bad_idx, 'length_km'] = 0.5             # km
```

## Cause 3: Non-existent junction index
Connecting an element to a junction index that does not exist raises an error or silently
leaves the element disconnected.
```python
all_j = set(net.junction.index)
for table in ['pipe', 'sink', 'source', 'ext_grid', 'valve', 'pump']:
    df = net[table]
    if df.empty:
        continue
    jcols = [c for c in df.columns if 'junction' in c]   # junction, from_junction, to_junction
    for col in jcols:
        bad = df[~df[col].isin(all_j)]
        if not bad.empty:
            print(f"net.{table}['{col}'] references missing junctions:", bad.index.tolist())
```

## Cause 4: Unphysical pressure or temperature values
Pressures in pandapipes are absolute [bar] and temperatures are in Kelvin, so physically
they should be > 0. Note `pn_bar` (junction) and `tfluid_k` (junction) are *initial values*
for the iteration, while `p_bar`/`t_k` on the `ext_grid` are the enforced boundary
conditions — but a non-positive value in any of them is still unphysical and a likely bug.
```python
print(net.junction[net.junction.pn_bar <= 0])     # initial pressure guess
print(net.ext_grid[net.ext_grid.p_bar <= 0])       # enforced pressure boundary
print(net.junction[net.junction.tfluid_k <= 0])    # initial / fluid temperature
```

## Cause 5: Wrong units (m vs km, m vs mm)
pandapipes is strict about units: pipe length in **km**, diameter in **mm**, pressure in
**bar**, mass flow in **kg/s**, temperature in **K**, height in **m**.
```python
# Wrong: a 500 m pipe entered as length_km=500 (means 500 km!)
# Right: length_km=0.5
print(net.pipe[['length_km', 'inner_diameter_mm']])  # sanity-check magnitudes
```

## Quick checklist
- [ ] `net.sink.mdot_kg_per_s.isna().any()` → False (and same for `net.source`)
- [ ] `(net.pipe.inner_diameter_mm > 0).all()` → True
- [ ] `(net.pipe.length_km > 0).all()` → True
- [ ] All junction indices referenced by elements exist in `net.junction.index`
- [ ] `net.junction.pn_bar.min() > 0` and `net.junction.tfluid_k.min() > 0`
