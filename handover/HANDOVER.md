# Handover: pandapipes contributions (continue on your own machine)

## Where everything is (your fork: https://github.com/AfaqJ/pandapipes)

| Branch | What | State |
|---|---|---|
| `feature/explain-diagnostic-layer` | `pandapipes.explain` optional local-LLM error explanations | pushed, CI green on the fork (18/18) before the last review-fix commit `ad92c71`; PR text ready |
| `feature/plotly-map-plot` | `create_map_figure`, token-free interactive map (replaces old PR #714) | pushed (`7e8f67b`), 618 tests pass locally; CI on fork not yet checked |

Both branches sit on top of upstream `e2nIEE/pandapipes` `develop` (b7e1784). Commits are authored by you, no extra attribution.

## 1. Get the code on your machine

```bash
cd ~ && git clone https://github.com/AfaqJ/pandapipes.git pandapipes-fork && cd pandapipes-fork
git remote add upstream https://github.com/e2nIEE/pandapipes.git && git fetch upstream
git checkout feature/plotly-map-plot
pip install -e ".[test,plotting]"
```

## 2. See the map and take the screenshot for the PR (needs internet)

Run the use case. It opens the interactive map in your browser; screenshot it (zoom into the town if you like):

```bash
python - <<'PY'
import pandas as pd, pandapipes as pp, pandapipes.networks as nw
from pandapipes.plotting import create_map_figure, convert_epsg_junction_geodata, convert_epsg_pipe_geodata

net = nw.schutterwald_heat()
names = net.junction.name; has_geo = net.junction_geodata.x.notna()
supply_of = pd.Series(names[has_geo].index, index=names[has_geo])
ret = names.index[~has_geo]
partners = supply_of[names[ret].str.removeprefix("return_")].values
shift = [5.0, -4.0]
net.junction_geodata.loc[ret, ["x", "y"]] = net.junction_geodata.loc[partners, ["x", "y"]].values + shift
is_ret = net.pipe.from_junction.isin(ret)
net.pipe_geodata.loc[is_ret, "coords"] = net.pipe_geodata.loc[is_ret, "coords"].apply(
    lambda c: [[x + shift[0], y + shift[1]] for x, y in c])
convert_epsg_junction_geodata(net, 31467, 4326); convert_epsg_pipe_geodata(net, 31467, 4326)
pp.pipeflow(net, mode="sequential", iter=100)
net.res_pipe["t_to_c"] = net.res_pipe.t_to_k - 273.15
create_map_figure(net, pipe_result="t_to_c", colorbar_title="Water temperature [°C]").show()
PY
```

Expected: the town of Schutterwald (near Offenburg, 48.46 N, 7.88 E) with red supply and blue/purple return lines, grey stubs = pipes without flow. The same tutorial: `tutorials/plotly_map_plotting.ipynb`.
(`heat_positron.html` sent in chat is the same figure as a standalone file: open it in a browser.)

Not verified yet: how the map looks WITH the street background (the sandbox had no access to tile servers). If something looks off, tell the assistant what you see.

## 3. Open the pull requests (base: `e2nIEE/pandapipes` `develop`)

- Map PR: use the pre-filled link in `pr2_link.txt` (text in `pr2_body.md`). Attach the screenshot where `<!-- ATTACH SCREENSHOT HERE -->` is, by dragging the image into the description.
- Explain PR: pre-filled link in `pr_link.txt` / text in `pr_body.md` (from the earlier step; branch `feature/explain-diagnostic-layer`). Screenshot there needs a local Ollama (`ollama pull llama3.2:1b`, then run `demo_explain.py` with `enable(model="llama3.2:1b")`).
- Then close old PR #714 with a comment linking the new map PR (PRs can't be deleted, only closed).
- Optional: open an upstream issue first (CONTRIBUTING asks for it for new features); draft in `issue_and_pr.md`.

## 4. Checks before/after opening

```bash
pytest src/pandapipes/test/plotting/test_plotly_map.py      # map tests
pytest --nbmake tutorials/plotly_map_plotting.ipynb          # tutorial
pytest -n auto                                               # full suite (what CI runs)
```
After pushing, watch the Actions tab on your fork; upstream CI also runs on the PR (a maintainer may need to approve the first run).

## 5. Known notes

- `create_map_figure` needs plotly >= 5.24 (optional extra). Tiles come from public servers (needs internet to see the background).
- Explain: Ollama only; `pandapipes.explain` ignores errors without any pandapipes frame.
- The old Claude-named branch is deleted from the fork; if one reappears, delete it: `git push origin --delete <name>`.
