"""
Generate a DRAFT of config/ffq_search_terms.csv.

Inputs
  data_raw/perls9.scn1.csv.label.doc, data_raw/perls9.scn2.csv.label.doc
      data dictionaries: the variable names in the FFQ data
  data_raw/ffq_grid2022_questions.csv
      the printed questionnaire (question type, section, portion as printed)

The draft is meant to be reviewed and edited by hand; the edited CSV (not this
script) is the source of truth used by the R pipeline. The script refuses to
overwrite an existing CSV unless run with --force.

Columns
  var, item          FFQ variable and its data-dictionary label
  data_file          which data file holds the variable (scn1 / scn2)
  item_type          frequency | passthru | type | supplement | amount | liver | behavior | diet | id | filler | other
                     (only `frequency` rows are searched in USDA / converted with the Grid2022 factors)
  search_terms       ';'-separated USDA search phrases, core food noun LAST
                     (the last word is used as the head word when choosing candidates)
  exclude            ';'-separated words; candidates whose description contains one are dropped
  food_group         questionnaire section
  form_label         the question text as printed on the form
  portion            the portion as printed on the form
  review             'check' = please look at this row; see `note`
  note               why the row needs a look
"""
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / ".here").exists())
DICTS = {
    "scn1": PROJECT_ROOT / "data_raw" / "perls9.scn1.csv.label.doc",
    "scn2": PROJECT_ROOT / "data_raw" / "perls9.scn2.csv.label.doc",
}
GRID_CSV = PROJECT_ROOT / "data_raw" / "ffq_grid2022_questions.csv"
OUT_CSV = PROJECT_ROOT / "config" / "ffq_search_terms.csv"

# ---------------------------------------------------------------------------
# search terms per frequency variable: "terms" or ("terms", "exclude", "note")
# ---------------------------------------------------------------------------
TERMS = {
    # dairy
    "skim.kids": "skim milk",
    "milk2": "low fat 1% milk; reduced fat 2% milk",
    "milk": "whole milk",
    "almond.milk": "almond milk",
    "soymilk.fort": "soy milk",
    "plant.milk": ("oat milk; rice milk; coconut milk beverage", "", "generic 'other plant-based milk'; pick representative foods"),
    "cream": ("half and half cream; sour cream", "fat free", ""),
    "cof.wht": ("nondairy coffee creamer", "fat free", ""),
    "yogurt.frozen": "frozen yogurt; sorbet; sherbet; light ice cream",
    "ice.cr": "ice cream",
    "bu": "butter; ghee",
    "margarine": "margarine",
    "spread.bu": "butter blend spread",   # butter with added oil
    "yog.plain": "plain yogurt",
    "yog.lt": ("light yogurt", "", "artificially sweetened; check FNDDS wording"),
    "yog": "fruit yogurt",
    "cot.ch": "cottage cheese; ricotta cheese",
    "cr.ch": "cream cheese",
    "oth.ch": ("cheddar cheese; mozzarella cheese; swiss cheese", "", "generic 'other cheese'; pick representative foods"),
    # fruits
    "raisgrp": "raisins; grapes",
    "prun": "prunes",
    "ban": "banana; plantain",
    "cant": "cantaloupe",
    "avocado": "avocado",
    "apple": ("raw apple; raw pear", "juice; sauce", ""),
    "a.j": "apple juice; apple cider",
    "tangerine": "tangerine; clementine; mandarin orange",
    "orang": ("raw orange", "juice", ""),
    "o.j.ca.d": "calcium fortified orange juice; vitamin D fortified orange juice",
    "o.j": ("orange juice", "fortified", ""),
    "grfrt": "grapefruit; grapefruit juice",
    "oth.f.j": ("fruit juice; grape juice; cranberry juice", "orange; apple; grapefruit", "generic 'other fruit juices'"),
    "straw": "strawberries",
    "blue": "blueberries",
    "peaches": "peach; plum",
    "apricot": "raw apricot; canned apricot",
    # vegetables
    "tom": ("raw tomato", "juice; sauce; soup", ""),
    "tom.j": "tomato juice; vegetable juice",
    "tom.s": "tomato sauce",
    "salsa": "salsa; taco sauce",
    "st.beans": "green beans",
    "humus": "hummus; chickpeas",
    "beans": "beans; lentils",
    "tofu": "tofu; soy burger; miso",
    "plant.burg": ("veggie burger", "", "generic 'other plant-based burger'"),
    "peas": ("green peas; lima beans; split pea soup", "", "'or soup' in label - confirm which soup"),
    "broc": "broccoli",
    "caul": "cauliflower",
    "cabb": "coleslaw; cabbage",
    "brusl": "brussels sprouts",
    "carrot.r": "raw carrots",
    "carrot.c": "cooked carrots",
    "corn": "corn",
    "mix.veg": "mixed vegetables",
    "swt.pot": "sweet potato; yam; sweet potato fries",
    "yel.sqs": "winter squash",
    "zuke": "eggplant; zucchini",
    "kale": "kale; arugula; mustard greens",
    "spin.ckd": "cooked spinach",
    "spin.raw": "raw spinach",
    "ice.let": "iceberg lettuce",
    "rom.let": "romaine lettuce; leaf lettuce",
    "peppers": "green pepper; red pepper; yellow pepper",
    "onions": "raw onion",   # onion as a garnish
    "onions1": "cooked onion",   # onion as a vegetable
    # eggs, meat, fish
    "eggs.omega": ("whole egg", "", "omega-3 fortified eggs; FNDDS may not distinguish"),
    "eggs": "whole egg",
    "hotdog": "beef hot dog",
    "chix.dog": "chicken hot dog; turkey hot dog; sausage; bacon",
    "chix.no.sand": "chicken sandwich; turkey sandwich; chicken frozen dinner",
    "chix.sk": "skin eaten chicken; skin eaten turkey",
    "chix.no": "skin not eaten chicken; skin not eaten turkey",
    "bacon": ("pork bacon", "turkey", ""),
    "bologna": "salami; bologna",
    "proc.mts": "pork sausage; beef sausage; kielbasa",
    "xtrlean.hamburg": "lean ground beef; extra lean ground beef",
    "hamb": "regular ground beef",
    "sand.bf.ham": ("roast beef sandwich; ham sandwich; lamb", "", "'as sandwich or mixed dish' - check candidates"),
    "pork": "pork chop; ham",
    "beef": "beef steak; beef roast; lamb",
    "tuna": "canned tuna",
    "fr.fish.kids": "fish sticks; fish cake",
    "shrimp.ckd": "shrimp; crab; scallops; clams",
    "dk.fish": "salmon; mackerel; sardines; swordfish; bluefish",
    "oth.fish": "cod; haddock; halibut",
    # grains
    "cold.cer": ("ready-to-eat cereal", "", "generic; brand-specific cereals are separate type variables"),
    "oatmeal.bran": "cooked oatmeal",
    "ckd.cer": "grits; cream of wheat",
    "wh.br": ("white bread; wheat bread; oatmeal bread", "whole", ""),
    "rye.br": "rye bread; pumpernickel bread",
    "dk.br": "whole wheat bread; multigrain bread",
    "crax.ww": "whole wheat crackers",
    "crax.oth": ("crackers", "whole", ""),
    "eng.muff": "bagel; english muffin; roll",
    "muffin": "muffin; biscuit",
    "pancak.all": "pancakes; waffles",
    "br.rice": "brown rice",
    "wh.rice": "white rice",
    "pasta.ww": "whole wheat pasta",
    "pasta": ("pasta", "whole", ""),
    "quinoa": ("quinoa; bulgur; barley", "", "generic 'other whole grain'"),
    "tortillas": "tortilla; burrito; quesadilla",
    "ff.pot": ("french fries", "sweet potato", ""),
    "pot": "baked potato; boiled potato; mashed potatoes",
    "snack.chip": "potato chips; corn chips; tortilla chips",
    "pizza.f.r": "pizza",
    # beverages
    "dietsoda.caf": ("diet cola", "caffeine free", ""),
    "dietsoda.nocaf": "caffeine free diet soft drink",
    "coke": ("cola", "diet; caffeine free", ""),
    "soda.nocaf": ("lemon-lime soft drink; ginger ale", "diet", ""),
    "punch": "fruit punch; lemonade; sports drink; sweetened tea",
    "beer": "beer; light beer; hard cider",
    "r.wine": "red wine",
    "w.wine": "white wine",
    "liq": "whiskey; vodka; rum; gin",
    "h2o": "tap water",
    "tea.decaf": ("decaffeinated tea", "herbal", ""),
    "tea": ("brewed tea", "herbal; decaffeinated", ""),
    "decaf": "decaffeinated coffee",
    "coff": ("brewed coffee", "decaffeinated", ""),
    "coff.drink": "cappuccino; latte",
    # sweets, snacks, misc
    "choc": "milk chocolate",
    "choc.dark": "dark chocolate",
    "candy.nuts": "chocolate candy bar",
    "candy": ("hard candy; gummy candy", "chocolate", ""),
    "coox.brn": "cookie; brownie",
    "coox.brn.home": "homemade cookie; homemade brownie",
    "donut": "doughnut",
    "cake.frost": "cake",
    "pie.comm": "pie",
    "jam": "jam; jelly",
    "p.bu": "peanut butter; almond butter",
    "popc": "popcorn",
    "s.roll.c": "sweet roll; danish",
    "snack.bar": "granola bar; snack bar",
    "energy.bar": "energy bar; protein bar",
    "diet.drk": ("meal replacement shake", "", "e.g. SlimFast; check FNDDS wording"),
    "meal.rpl.drk": ("nutritional shake", "", "Ensure; check FNDDS wording"),
    "pretzel": "pretzels",
    "nuts": "peanuts",
    "walnuts": "walnuts",
    "oth.nuts": "almonds; cashews; mixed nuts",
    "dr.cranb": "dried cranberries",
    "mix.dr.frt": "mixed dried fruit",
    "oth.bran": "oat bran; wheat bran",
    "chowder": "clam chowder; cream soup",
    "tom.soup": "tomato soup",
    "catsup": "ketchup",
    "flax": "flaxseed",
    "seeds": "pumpkin seeds; sunflower seeds",
    "garlic2": "garlic",
    "olives": "olives",
    "olive.oil": "olive oil",   # added to food or bread
    "mayo.d": "light mayonnaise; olive oil mayonnaise",
    "mayo": ("mayonnaise", "light", ""),
    "o.v": "salad dressing",
    "artif.sweet": "sugar substitute",
}

SUPPLEMENT_SECTIONS = {"Multivitamins", "Individual vitamins (not counting multivitamins)", "Other supplements"}


def read_dict(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            var, label = line.split("=", 1)
            rows.append((var.strip(), " ".join(label.split())))
    return pd.DataFrame(rows, columns=["var", "item"])


def grid_by_var(grid: pd.DataFrame) -> dict:
    """var -> (grid row, role) where role is 'var' or 'passthru'"""
    out = {}
    for _, r in grid.iterrows():
        for col, role in (("var", "var"), ("passthru_var", "passthru")):
            if pd.notna(r[col]):
                for v in str(r[col]).split("|"):
                    if v:
                        out[v] = (r, role)
    return out


def classify(var: str, g) -> str:
    if var == "id":
        return "id"
    if g is None:
        return "filler" if var.startswith("blank") else "other"
    r, role = g
    if role == "passthru" or r["response_type"] == "passthru":
        return "passthru"
    if r["response_type"] == "frequency":
        return "frequency"
    if r["section"] in SUPPLEMENT_SECTIONS:
        return "supplement"
    if var == "sug":
        return "amount"
    if r["section"] == "Liver":
        return "liver"            # food frequency on its own 5-level scale
    if var in ("ffh", "ffa", "toast"):
        return "behavior"
    if r["section"] == "Diet":
        return "diet"
    return "type"


def main(force: bool) -> None:
    if OUT_CSV.exists() and not force:
        sys.exit(f"{OUT_CSV} already exists (it may contain manual edits). Use --force to overwrite.")

    d = pd.concat([read_dict(p).assign(data_file=k) for k, p in DICTS.items()])
    d = (d.groupby(["var", "item"], sort=False)["data_file"].agg("|".join).reset_index())

    grid = pd.read_csv(GRID_CSV, dtype=str)
    gmap = grid_by_var(grid)

    rows = []
    for _, r in d.iterrows():
        g = gmap.get(r["var"])
        item_type = classify(r["var"], g)
        terms, exclude, note = "", "", ""
        food_group = form_label = portion = None
        if g is not None:
            gr = g[0]
            food_group = gr["section"]
            form_label = gr["item_label"] if pd.isna(gr["group_label"]) else f"{gr['group_label']}: {gr['item_label']}"
            portion = gr["portion_text"]
        if item_type == "frequency":
            if r["var"] not in TERMS:
                sys.exit(f"no search terms for frequency variable {r['var']!r}")
            spec = TERMS[r["var"]]
            terms, exclude, note = (spec, "", "") if isinstance(spec, str) else spec
        elif item_type == "other":
            note = "unclassified - set item_type by hand"
        # no portion printed on the form (confirmed against the PDF): portion stays blank, not a review item
        info = "no portion printed on the form" if item_type == "frequency" and pd.isna(portion) else ""
        rows.append({
            "var": r["var"],
            "item": r["item"],
            "data_file": r["data_file"],
            "item_type": item_type,
            "search_terms": terms,
            "exclude": exclude,
            "food_group": food_group,
            "form_label": form_label,
            "portion": portion,
            "review": "check" if note else "",
            "note": "; ".join(x for x in [note, info] if x),
        })

    out = pd.DataFrame(rows)
    unused = set(TERMS) - set(out.loc[out["item_type"] == "frequency", "var"])
    if unused:
        sys.exit(f"TERMS has vars that are not frequency items: {sorted(unused)}")

    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"wrote {OUT_CSV} ({len(out)} vars)")
    print(out["item_type"].value_counts().to_string())
    print("rows flagged for review:", (out["review"] == "check").sum())


if __name__ == "__main__":
    main(force="--force" in sys.argv)
