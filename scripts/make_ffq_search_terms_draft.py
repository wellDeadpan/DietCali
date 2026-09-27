"""
Generate a DRAFT of config/ffq_search_terms.csv from the parsed FFQ item map.

The draft is meant to be reviewed and edited by hand; the edited CSV (not this
script) is the source of truth used by the R pipeline. The script refuses to
overwrite an existing CSV unless run with --force.

Columns
  var, item          FFQ variable and its original label
  item_type          frequency | type | passthru | supplement | amount | id | filler | other
                     (only `frequency` rows are searched in USDA / converted to servings)
  search_terms       ';'-separated USDA search phrases, core food noun LAST
                     (the last word is used as the head word when choosing candidates)
  exclude            ';'-separated words; candidates whose description contains one are dropped
  food_group, portion, matched_food_item, match_score
                     carried over from the portion-table fuzzy match (master_food_table.csv)
  portion_fix        set when PORTION_OVERRIDE corrected a wrong/missing fuzzy match
  review             'check' = please look at this row; see `note`
  note               why the row needs a look
"""
import re
import sys
from pathlib import Path

import pandas as pd
import pyreadr

PROJECT_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / ".here").exists())
IN_RDS = PROJECT_ROOT / "cache" / "ffq_item_map_parsed.rds"
MASTER_CSV = PROJECT_ROOT / "data_raw" / "master_food_table.csv"
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
    "spread.bu": ("butter blend spread", "", "spreadable butter (butter + oil)"),
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

# ---------------------------------------------------------------------------
# portion-table rows (master_food_table.csv food_item) where the notebook's
# fuzzy match was wrong or missing
# ---------------------------------------------------------------------------
PORTION_OVERRIDE = {
    # wrong match -> wrong portion
    "corn": "Corn",                                              # was potato chips
    "coff": "Coffee with caffeine",                              # was sweet roll
    # swapped pairs (same portion, fixed for correctness)
    "yog.lt": "Yogurt - Artificially sweetened",
    "yog": "Yogurt - Sweetened",
    "tangerine": "Tangerines / clementines / mandarin oranges",
    "orang": "Oranges",
    "chix.sk": "Other chicken or turkey with skin (incl. ground)",
    "chix.no": "Other chicken or turkey without skin",
    "dietsoda.caf": "Low-calorie carbonated beverage with caffeine",
    # no match
    "spread.bu": "Butter with added oil (spread)",
    "o.j.ca.d": "Orange juice (calcium or vitamin D fortified)",
    "onions": "Onions as garnish or salad",
    "onions1": "Onions cooked or rings",
    "fr.fish.kids": "Breaded fish / fish sticks (store bought)",
    "ckd.cer": "Other cooked breakfast cereal (including grits)",
    "pasta.ww": "Whole grain pasta (e.g., spaghetti, macaroni)",
    "quinoa": "Other whole grains (quinoa, barley, spelt, etc.)",
    "snack.chip": "Potato chips or corn/tortilla chips",
    "dietsoda.nocaf": "Other low-calorie carbonated beverage without caffeine",
    "coke": "Carbonated beverage with caffeine & sugar",
    "punch": "Other sugar-sweetened beverages (juice drinks, lemonade, sports drinks, sweetened tea)",
    "s.roll.c": "Sweet roll / coffee cake / pastry",
    "snack.bar": "Snack bars (Kind, Kashi, granola)",
    "oth.bran": "Oat bran / wheat bran added to food",
}

# variables that are not food-frequency questions
SUPPLEMENT_RANGE = ("multvit", "otherptb")      # contiguous block of supplement questions
CEREAL_BRANDS = {"cer", "c.flk.K", "cheerio", "fr.miniwht", "natural.q",
                 "hon.bun.oats", "spec.k", "rz.b.k", "sh.wht"}


def classify(var: str, item: str, in_supp_block: bool) -> str:
    it = item.lower()
    if var == "id":
        return "id"
    if it.strip() == "filler":
        return "filler"
    if "passthru" in it or re.search(r"\bptb\b", it) or var == "cerpt":
        return "passthru"
    if in_supp_block:
        return "supplement"
    if var == "sug":
        return "amount"
    if var in TERMS:          # before the 'type' check: e.g. "Olives, any type" is a food
        return "frequency"
    if var in CEREAL_BRANDS or re.search(r"\btype\b", it):
        return "type"
    return "other"


def main(force: bool) -> None:
    if OUT_CSV.exists() and not force:
        sys.exit(f"{OUT_CSV} already exists (it may contain manual edits). Use --force to overwrite.")

    d = pyreadr.read_r(str(IN_RDS))[None].reset_index(drop=True)
    g = (d.groupby(["var", "item"], sort=False)
           .agg(food_group=("food_group", "first"), portion=("portion", "first"),
                matched_food_item=("matched_food_item", "first"), match_score=("match_score", "first"))
           .reset_index())

    master = pd.read_csv(MASTER_CSV, encoding="utf-8-sig").set_index("food_item")
    bad = set(PORTION_OVERRIDE.values()) - set(master.index)
    if bad:
        sys.exit(f"PORTION_OVERRIDE refers to unknown master_food_table items: {sorted(bad)}")
    for var, food_item in PORTION_OVERRIDE.items():
        i = g.index[g["var"] == var][0]
        old = g.at[i, "matched_food_item"]
        g.at[i, "matched_food_item"] = food_item
        g.at[i, "food_group"] = master.at[food_item, "food_group"]
        g.at[i, "portion"] = master.at[food_item, "portion"]
        g.at[i, "match_score"] = None
        g.at[i, "portion_fix"] = "no match" if pd.isna(old) else f"was: {old}"

    vars_ = g["var"].tolist()
    lo, hi = vars_.index(SUPPLEMENT_RANGE[0]), vars_.index(SUPPLEMENT_RANGE[1])

    rows = []
    for i, r in g.iterrows():
        item_type = classify(r["var"], r["item"], lo <= i <= hi)
        terms, exclude, note = "", "", ""
        if item_type == "frequency":
            spec = TERMS[r["var"]]
            terms, exclude, note = (spec, "", "") if isinstance(spec, str) else spec
            if pd.isna(r["portion"]) or str(r["portion"]).strip().lower() in ("", "nan"):
                note = "; ".join(x for x in [note, "no portion in master_food_table"] if x)
        # portion info is only meaningful for frequency items (fuzzy match misfires otherwise)
        keep_portion = item_type == "frequency"
        rows.append({
            "var": r["var"],
            "item": r["item"],
            "item_type": item_type,
            "search_terms": terms,
            "exclude": exclude,
            "food_group": r["food_group"] if keep_portion else None,
            "portion": r["portion"] if keep_portion else None,
            "matched_food_item": r["matched_food_item"] if keep_portion else None,
            "match_score": r["match_score"] if keep_portion else None,
            "portion_fix": r.get("portion_fix") if keep_portion and pd.notna(r.get("portion_fix")) else None,
            "review": "check" if (note or item_type == "other") else "",
            "note": note if item_type != "other" else "unclassified - set item_type by hand",
        })

    out = pd.DataFrame(rows)
    unused = set(TERMS) - set(out["var"])
    if unused:
        sys.exit(f"TERMS has vars not in the item map: {sorted(unused)}")

    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"wrote {OUT_CSV} ({len(out)} vars)")
    print(out["item_type"].value_counts().to_string())
    print("rows flagged for review:", (out["review"] == "check").sum())


if __name__ == "__main__":
    main(force="--force" in sys.argv)
