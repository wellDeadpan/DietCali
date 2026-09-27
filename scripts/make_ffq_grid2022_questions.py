"""
Build data_raw/ffq_grid2022_questions.csv: the Harvard Grid 2022 FFQ
(FINAL-GRID-2022 proof, 4 pages) transcribed by hand, one row per question /
food item, linked to the variable names in the perls9 data dictionaries
(data_raw/perls9.scn1.csv.label.doc, data_raw/perls9.scn2.csv.label.doc).

Run from anywhere inside the project:  python3 scripts/make_ffq_grid2022_questions.py
The script checks that every variable exists in a dictionary and reports
dictionary variables that have no question.
"""
import csv
import re
from pathlib import Path

PROJECT_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / ".here").exists())
DICTS = {
    "scn1": PROJECT_ROOT / "data_raw" / "perls9.scn1.csv.label.doc",
    "scn2": PROJECT_ROOT / "data_raw" / "perls9.scn2.csv.label.doc",
}
OUT = PROJECT_ROOT / "data_raw" / "ffq_grid2022_questions.csv"


def read_dict(path):
    """var = label lines -> {var: label}"""
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            var, label = line.split("=", 1)
            out[var.strip()] = label.strip()
    return out

F9 = ("Never, or less than once per month|1–3 per month|1 per week|2–4 per week|5–6 per week|"
      "1 per day|2–3 per day|4–5 per day|6+ per day")
rows = []
def add(page, qno, section, item_label, rtype, options, var="", group="", portion="", examples="",
        instruction="", passthru_var="", note=""):
    rows.append(dict(page=page, question_no=qno, section=section, group_label=group, item_label=item_label,
                     portion_text=portion, examples=examples, instruction=instruction,
                     response_type=rtype, response_options=options, var=var,
                     passthru_var=passthru_var, note=note))
def food(page, section, label, var, portion="", examples="", instruction="", group="", note=""):
    add(page, "5", section, label, "frequency", F9, var, group, portion, examples, instruction, note=note)

# ---------------- page 1: Q1-Q4 ----------------
S = "Multivitamins"
add(1, "1", S, "Do you currently take multivitamins? (Please report other individual vitamins in the next section.)", "single_choice", "No|Yes", "multvit")
add(1, "1a", S, "How many do you take per week?", "single_choice", "2 or less|3–5|6–9|10 or more", "mulfrq")
add(1, "1b", S, "Is this usually a gummy vitamin?", "single_choice", "No|Yes", "gummy.type")
add(1, "1c", S, "Is the type you most often take labeled for:", "single_choice", "Men|Women|Both", "other.type")
add(1, "1d", S, "What specific brand (or equivalency) do you most often take? (Select ONE ONLY)", "single_choice",
    "Centrum silver or Senior Vit.|Centrum or generic equiv.|One-A-Day or equiv.|One-A-Day Teens or equiv.|"
    "Flintstones or Kids Multi equiv.|Prenatal|Eye Health|Whole Foods/Vegetarian/Fruit Bites|"
    "Other Multivitamins (with minerals)|Other Multivitamins (without minerals)|Other (write in)",
    "centrum.silver|centrum|oneaday|teen.vit|kids.vit|prenatal|areds|veg.vit|other.mvmin|other.mvnomin|other.mv",
    passthru_var="brndpt", note="each option is its own variable")
S = "Individual vitamins (not counting multivitamins)"
SEAS = "No|Yes, seasonal only|Yes, most months"
def vit(label, use_opts, use_var, dose_opts, dose_var, instruction="", dose_label="Dose per day"):
    add(1, "1", S, label, "single_choice", use_opts, use_var, instruction=instruction)
    add(1, "1", S, f"{label}: {dose_label} (if yes)", "single_choice", dose_opts, dose_var, group=label)
vit("Vitamin A", SEAS, "vitamin.a", "Less than 3,000 mcg|3,000 to 4,500 mcg|4,800 to 6,600 mcg|6,900 mcg or more|Don't know", "ad")
vit("Potassium", "No|Yes", "k", "Less than 2.5 mEq (100 mg)|3 to 9 mEq|10 to 19 mEq|20 mEq or more|Don't know", "kd")
vit("Vitamin C", SEAS, "vitamin.c", "Less than 400mg|400 to 700 mg|750 to 1250 mg|1300 mg or more|Don't know", "cd")
vit("Vitamin B6", "No|Yes", "b6", "Less than 50 mg|50 to 99 mg|100 to 149 mg|150 mg or more|Don't know", "b6d")
vit("Vitamin E", "No|Yes", "vitamin.e", "Less than 100 mg|100 to 300 mg|301 to 400 mg|401 mg or more|Don't know", "ed")
add(1, "1", S, "Vitamin E: Type (if yes)", "single_choice", "Natural|Regular (dl)|Unknown", "etype", group="Vitamin E")
vit("Calcium", "No|Yes", "calcium", "Less than 600 mg|600 to 900 mg|901 to 1500 mg|1501 mg or more|Don't know", "cad",
    instruction="Include Calcium in Tums, etc.", dose_label="Dose per day (elemental calcium)")
vit("Vitamin D", SEAS, "vitamin.d", "< 1000 IU's (< 25 mcg)|1000-1999 IU's (25-49 mcg)|2000-4999 IU's (50-124 mcg)|5000+ IU's (125+ mcg)", "vitdd",
    instruction="in calcium supplement or separately")
vit("Zinc", "No|Yes", "zinc", "Less than 31 mg|31 to 74 mg|75 to 100 mg|101 mg or more|Don't know", "znd")
add(1, "2", "Other supplements", "Are there other supplements that you take on a regular basis?", "multi_choice",
    "Metamucil/Citrucel|B-Complex|Flax Seed Oil|Beta-carotene|Iron|Vitamin B12|Magnesium|Niacin|Folic Acid|Fish Oil|"
    "Lycopene|Glucosamine/Chondroitin|Coenzyme Q10|Cod Liver Oil|Selenium|Probiotics|Biotin|Turmeric/Curcumin|Other (write in)",
    "metamucil|bcompl.06|linseed|bcar|iron|b12|magnesium|niacin2|folic.acid|omega.3.epa|lyco|gluchon|coq10|cod.liv.oil|sel|probiotics|biotin|tumeric|others",
    passthru_var="otherptb", note="each option is its own variable")
add(1, "3", "Added sugar", "How many teaspoons of sugar do you add to your beverages or food each day?", "single_choice",
    "Zero|1 tsp.|2 tsp.|3 tsp.|4 tsp.|5 tsp.|6 tsp.|7 tsp.|8 tsp.|9 tsp.|10 tsp.|More than 10 (write number)", "sug",
    note="'sugcht' (Sugar cheat bubble) in the data dictionary may relate to the write-in box - unconfirmed")
add(1, "4", "Cold breakfast cereal", "What brand and type of cold breakfast cereal do you most often eat?", "text",
    "Specify cereal brand & type (e.g., Kellogg's Raisin Bran)|Don't eat cold breakfast cereal", "cer",
    passthru_var="cerpt", note="'Don't eat cold breakfast cereal' = cerpt (No Cereal)")
add(1, "4", "Cold breakfast cereal", "Cereal brand code (coded bubbles in left margin)", "single_choice",
    "CF|CH|FM|GR|HB|K|RB|SW", "c.flk.K|cheerio|fr.miniwht|natural.q|hon.bun.oats|spec.k|rz.b.k|sh.wht",
    note="code -> variable mapping inferred from names: CF Corn Flakes, CH Cheerios, FM Frosted Mini Wheats, GR Granola, "
         "HB Honey Bunches of Oats, K Special K, RB Raisin Bran, SW Shredded Wheat")

# ---------------- Q5 food frequency ----------------
S = "Dairy Foods"
add(1, "5", S, "Dairy Foods section passthru (P)", "passthru", "P", "dpt")
g = "Milk (8 oz. glass)"
for lab, v in [("Skim milk", "skim.kids"), ("1 or 2 % milk", "milk2"), ("Whole milk", "milk"),
               ("Almond milk", "almond.milk"), ("Soy milk", "soymilk.fort"), ("Other plant-based milk", "plant.milk")]:
    food(1, S, lab, v, "8 oz. glass", group=g)
food(1, S, "Cream, e.g., coffee, sour (exclude fat free) (1 Tbs)", "cream", "1 Tbs", "coffee, sour", "exclude fat free")
food(1, S, "Non-dairy coffee whitener (exclude fat free) (1 Tbs)", "cof.wht", "1 Tbs", "", "exclude fat free")
food(1, S, "Frozen yogurt, sherbet, or low-fat ice cream (1 cup)", "yogurt.frozen", "1 cup")
food(1, S, "Regular ice cream (1 cup)", "ice.cr", "1 cup")
g = "Spreads added to food or bread; exclude use in cooking"
food(1, S, "Pure butter or ghee", "bu", group=g, instruction="exclude use in cooking", note="no portion printed")
food(1, S, "Margarine", "margarine", group=g, instruction="exclude use in cooking", note="no portion printed")
food(1, S, "Butter with added oil (e.g., Land O Lakes Butter with Canola Oil)", "spread.bu", examples="Land O Lakes Butter with Canola Oil",
     group=g, instruction="exclude use in cooking", note="no portion printed")
g = "Yogurt (4–6 oz.) Include drinkable"
food(1, S, "Plain", "yog.plain", "4–6 oz.", group=g, instruction="include drinkable")
food(1, S, "Artificially sweetened (e.g., light peach)", "yog.lt", "4–6 oz.", "light peach", "include drinkable", group=g)
food(1, S, "Sweetened (e.g., strawberry, vanilla)", "yog", "4–6 oz.", "strawberry, vanilla", "include drinkable", group=g)
add(1, "5", S, "What type of yogurt do you most often eat? (Mark all that apply.)", "multi_choice",
    "Greek|Regular|Full Fat|Reduced Fat", "yog.greek|yog.reg|yog.full|yog.low", passthru_var="yog.pt",
    note="each option is its own variable")
food(1, S, "Cottage or ricotta cheese (1/2 cup)", "cot.ch", "1/2 cup")
food(1, S, "Cream cheese (1 oz.)", "cr.ch", "1 oz.")
food(1, S, "Other cheese, e.g., American, cheddar, etc., plain or as part of a dish (1 slice or 1 oz. serving)", "oth.ch",
     "1 slice or 1 oz. serving", "American, cheddar, etc.", "plain or as part of a dish")
add(1, "5", S, "What type of cheese do you most often eat?", "single_choice", "Regular|Low-fat or Lite|Fat Free|None",
    "ch.reg|ch.lofat|ch.nofat|ch.none", passthru_var="ch.pt", note="each option is its own variable")

S = "Fruits"
add(2, "5", S, "Fruits section passthru (P)", "passthru", "P", "fpt")
for lab, v, por, ex in [
    ("Raisins (1 oz. or small pack) or grapes (1/2 cup)", "raisgrp", "raisins 1 oz. or small pack; grapes 1/2 cup", ""),
    ("Prunes or dried plums (1/2 cup canned or 1/4 cup dried)", "prun", "1/2 cup canned or 1/4 cup dried", ""),
    ("Bananas (1) or plantain (1/2)", "ban", "bananas 1; plantain 1/2", ""),
    ("Cantaloupe (1/4 melon)", "cant", "1/4 melon", ""),
    ("Avocado (1/2 fruit or 1/2 cup)", "avocado", "1/2 fruit or 1/2 cup", ""),
    ("Fresh apples or pears (1)", "apple", "1", ""),
    ("Apple juice or cider (small glass)", "a.j", "small glass", ""),
    ("Tangerines, clementines, mandarin oranges (1)", "tangerine", "1", ""),
    ("Oranges (1)", "orang", "1", "")]:
    food(2, S, lab, v, por, ex)
g = "Orange juice (small glass)"
food(2, S, "Calcium or Vit. D fortified", "o.j.ca.d", "small glass", group=g)
food(2, S, "Regular (not calcium fortified)", "o.j", "small glass", group=g)
for lab, v, por, ex in [
    ("Grapefruit (1/2) or grapefruit juice (small glass)", "grfrt", "grapefruit 1/2; juice small glass", ""),
    ("Other fruit juices (e.g., cranberry, grape) (small glass)", "oth.f.j", "small glass", "cranberry, grape"),
    ("Strawberries, fresh, frozen or canned (1/2 cup)", "straw", "1/2 cup", ""),
    ("Blueberries, fresh, frozen or canned (1/2 cup)", "blue", "1/2 cup", ""),
    ("Peaches or plums (1 fresh or 1/2 cup canned)", "peaches", "1 fresh or 1/2 cup canned", ""),
    ("Apricots (1 fresh, 1/2 cup canned or 5 dried)", "apricot", "1 fresh, 1/2 cup canned or 5 dried", "")]:
    food(2, S, lab, v, por, ex)

S = "Vegetables"
add(2, "5", S, "Vegetables section passthru (P)", "passthru", "P", "vpt")
for lab, v, por, ex in [
    ("Tomatoes (2 slices)", "tom", "2 slices", ""),
    ("Tomato juice or V-8 juice (small glass)", "tom.j", "small glass", ""),
    ("Tomato sauce (1/2 cup) e.g., spaghetti sauce", "tom.s", "1/2 cup", "spaghetti sauce"),
    ("Salsa, picante or taco sauce (1/4 cup)", "salsa", "1/4 cup", ""),
    ("String beans (1/2 cup)", "st.beans", "1/2 cup", ""),
    ("Hummus (1/4 cup), garbanzo or chickpeas (1/2 cup)", "humus", "hummus 1/4 cup; garbanzo/chickpeas 1/2 cup", ""),
    ("Beans or lentils, baked, dried (1/2 cup) or soup", "beans", "1/2 cup or soup", ""),
    ("Soy burger, tofu, miso or other soy protein", "tofu", "", ""),
    ("Other plant-based burger, e.g., Beyond Meat, Lightlife (1 patty)", "plant.burg", "1 patty", "Beyond Meat, Lightlife"),
    ("Peas or lima beans (1/2 cup fresh, frz., canned) or soup", "peas", "1/2 cup fresh, frz., canned or soup", ""),
    ("Broccoli (1/2 cup)", "broc", "1/2 cup", ""),
    ("Cauliflower (1/2 cup)", "caul", "1/2 cup", ""),
    ("Cabbage or coleslaw (1/2 cup)", "cabb", "1/2 cup", ""),
    ("Brussels sprouts (1/2 cup)", "brusl", "1/2 cup", ""),
    ("Carrots, raw (1/2 carrot or 2–4 sticks)", "carrot.r", "1/2 carrot or 2–4 sticks", ""),
    ("Carrots, cooked (1/2 cup) or carrot juice (2–3 oz.)", "carrot.c", "carrots 1/2 cup; juice 2–3 oz.", ""),
    ("Corn (1 ear or 1/2 cup frozen or canned)", "corn", "1 ear or 1/2 cup frozen or canned", ""),
    ("Mixed or stir fry vegetables (1/2 cup) or soup", "mix.veg", "1/2 cup or soup", ""),
    ("Yams or sweet potatoes, include sweet potato fries, (1/2 cup)", "swt.pot", "1/2 cup", ""),
    ("Dark orange (winter) squash (1/2 cup)", "yel.sqs", "1/2 cup", ""),
    ("Eggplant, zucchini or other summer squash (1/2 cup)", "zuke", "1/2 cup", ""),
    ("Kale, arugula or mustard greens (1/2 cup)", "kale", "1/2 cup", ""),
    ("Spinach, cooked (1/2 cup)", "spin.ckd", "1/2 cup", ""),
    ("Spinach, raw as in salad (1 cup)", "spin.raw", "1 cup", ""),
    ("Iceberg or head lettuce (1 serving)", "ice.let", "1 serving", ""),
    ("Romaine or leaf lettuce (1 serving)", "rom.let", "1 serving", ""),
    ("Peppers: green, yellow or red (2 rings or 1/4 small)", "peppers", "2 rings or 1/4 small", ""),
    ("Onions as a garnish or in salad (1 slice)", "onions", "1 slice", ""),
    ("Onions as a cooked vegetable or rings (1/2 cup) or soup", "onions1", "1/2 cup or soup", "")]:
    instr = "include sweet potato fries" if v == "swt.pot" else ""
    food(2, S, lab, v, por, ex, instr, note="no portion printed" if not por else "")

S = "Eggs, Meat, etc."
add(2, "5", S, "Eggs, Meat, etc. section passthru (P)", "passthru", "P", "eggspt")
g = "Eggs (1)"
food(2, S, "Omega-3 fortified including yolk", "eggs.omega", "1", group=g)
food(2, S, "Regular eggs including yolk", "eggs", "1", group=g)
food(2, S, "Beef hot dogs (1)", "hotdog", "1")
food(2, S, "Chicken or turkey hot dogs, sausage (1) or bacon (2 slices)", "chix.dog", "hot dog/sausage 1; bacon 2 slices")
food(2, S, "Chicken/turkey sandwich or frozen dinner", "chix.no.sand", note="no portion printed")
food(2, S, "Other chicken or turkey, with skin (3 oz.) – including ground", "chix.sk", "3 oz.", instruction="including ground")
food(2, S, "Other chicken or turkey, without skin (3 oz.)", "chix.no", "3 oz.")
food(2, S, "Bacon (exclude turkey bacon) (2 slices)", "bacon", "2 slices", instruction="exclude turkey bacon")

S = "Meat, Fish"
add(3, "5", S, "Meat, Fish section passthru (P)", "passthru", "P", "mpt", note="data dictionary label: 'eggom18dats, etc. - Passthru'")
food(3, S, "Salami, bologna, or other processed meat sandwiches", "bologna", note="no portion printed")
food(3, S, "Sausage or kielbasa (pork or beef) etc. (2 oz. or 2 links)", "proc.mts", "2 oz. or 2 links")
g = "Hamburger (1 patty)"
food(3, S, "Lean or extra lean", "xtrlean.hamburg", "1 patty", group=g)
food(3, S, "Regular", "hamb", "1 patty", group=g)
food(3, S, "Beef, pork, or lamb as a sandwich or mixed dish, e.g., stew, casserole, lasagna, frozen dinners, etc.", "sand.bf.ham",
     examples="stew, casserole, lasagna, frozen dinners", note="no portion printed")
food(3, S, "Pork as a main dish, e.g., ham or chops (4–6 oz.)", "pork", "4–6 oz.", "ham or chops")
food(3, S, "Beef or lamb as a main dish, e.g., steak, roast (4–6 oz.)", "beef", "4–6 oz.", "steak, roast")
food(3, S, "Canned tuna fish (3–4 oz.)", "tuna", "3–4 oz.")
food(3, S, "Breaded fish, pieces or sticks (1 serving, store bought)", "fr.fish.kids", "1 serving", instruction="store bought")
food(3, S, "Shellfish, e.g., shrimp, crab, scallops, clams as main dish", "shrimp.ckd", examples="shrimp, crab, scallops, clams",
     instruction="as main dish", note="no portion printed")
food(3, S, "Dark meat fish, e.g., tuna steak, mackerel, salmon, sardines, bluefish, swordfish (3–5 oz.)", "dk.fish", "3–5 oz.",
     "tuna steak, mackerel, salmon, sardines, bluefish, swordfish")
food(3, S, "Other fish, e.g., cod, haddock, halibut (3–5 oz.)", "oth.fish", "3–5 oz.", "cod, haddock, halibut")

S = "Breads, Cereals, Starches"
add(3, "5", S, "Breads, Cereals, Starches section passthru (P)", "passthru", "P", "bpt")
food(3, S, "Cold breakfast cereal (1 serving)", "cold.cer", "1 serving")
food(3, S, "Cooked oatmeal/cooked oat bran (including instant) (1 cup)", "oatmeal.bran", "1 cup", instruction="including instant")
food(3, S, "Other cooked breakfast cereal, including grits (1 cup)", "ckd.cer", "1 cup", instruction="including grits")
g = "Bread or Pita (1 slice)"
food(3, S, "White, wheat, oatmeal (not whole grain)", "wh.br", "1 slice", group=g, instruction="not whole grain")
food(3, S, "Rye/Pumpernickel", "rye.br", "1 slice", group=g)
food(3, S, "Whole wheat, whole grain oat, whole multigrain", "dk.br", "1 slice", group=g)
g = "Crackers (6)"
food(3, S, "Whole grain/whole wheat", "crax.ww", "6", group=g)
food(3, S, "Other crackers", "crax.oth", "6", group=g)
for lab, v, por, ex in [
    ("Bagels, English muffins, or rolls (1)", "eng.muff", "1", ""),
    ("Muffins or biscuits (1)", "muffin", "1", ""),
    ("Pancakes or waffles (2 small pieces)", "pancak.all", "2 small pieces", ""),
    ("Brown rice (1 cup)", "br.rice", "1 cup", ""),
    ("White rice (1 cup)", "wh.rice", "1 cup", ""),
    ("Whole grain pasta, e.g., spaghetti, macaroni (1 cup)", "pasta.ww", "1 cup", "spaghetti, macaroni"),
    ("Other pasta (not whole grain), e.g., spaghetti, noodles, macaroni, etc. (1 cup)", "pasta", "1 cup", "spaghetti, noodles, macaroni"),
    ("Other whole grains, e.g., quinoa, barley, spelt, etc. (1 cup)", "quinoa", "1 cup", "quinoa, barley, spelt"),
    ("Tortillas: corn or flour, e.g., burritos, quesadillas etc. (2)", "tortillas", "2", "burritos, quesadillas"),
    ("French Fries, exclude sweet potato fries (6 oz. or 1 serving)", "ff.pot", "6 oz. or 1 serving", ""),
    ("Potatoes, baked, boiled (1) or mashed (1 cup)", "pot", "baked/boiled 1; mashed 1 cup", ""),
    ("Potato chips or corn/tortilla chips (small bag or 1 oz.)", "snack.chip", "small bag or 1 oz.", ""),
    ("Pizza (2 slices)", "pizza.f.r", "2 slices", "")]:
    instr = {"pasta": "not whole grain", "ff.pot": "exclude sweet potato fries"}.get(v, "")
    food(3, S, lab, v, por, ex, instr)

S = "Beverages"
add(3, "5", S, "Beverages section passthru (P)", "passthru", "P", "bvpt")
CARB = "Consider the serving size as 1 glass, bottle or can for these carbonated beverages"
g = "Carbonated beverages – Low-Calorie (sugar-free) types"
food(3, S, "Low-calorie beverage with caffeine, e.g., Diet Coke", "dietsoda.caf", "1 glass, bottle or can", "Diet Coke", CARB, group=g)
food(3, S, "Other low-cal bev. without caffeine, e.g., Diet 7-Up", "dietsoda.nocaf", "1 glass, bottle or can", "Diet 7-Up", CARB, group=g)
g = "Carbonated beverages – Regular types (not sugar-free)"
food(3, S, "Carbonated beverage with caffeine & sugar, e.g., Coke, Pepsi, Mt. Dew, Dr. Pepper", "coke", "1 glass, bottle or can",
     "Coke, Pepsi, Mt. Dew, Dr. Pepper", CARB, group=g)
food(3, S, "Other carbonated beverage with sugar, e.g., 7-Up, Root Beer, Ginger Ale, Caffeine-Free Coke", "soda.nocaf",
     "1 glass, bottle or can", "7-Up, Root Beer, Ginger Ale, Caffeine-Free Coke", CARB, group=g)
g = "Other beverages"
for lab, v, por, ex, instr in [
    ("Other sugared beverages, e.g., Punch, lemonade, sports drinks, or sugared ice tea (1 glass, bottle, can)", "punch",
     "1 glass, bottle, can", "Punch, lemonade, sports drinks, sugared ice tea", ""),
    ("Beer, regular, light or hard cider (1 glass, bottle, can)", "beer", "1 glass, bottle, can", "", ""),
    ("Red wine (5 oz. glass)", "r.wine", "5 oz. glass", "", ""),
    ("White wine (5 oz. glass)", "w.wine", "5 oz. glass", "", ""),
    ("Liquor, e.g., vodka, gin, hard seltzer, etc. (e.g., White Claw, Truly Seltzer, Mikes Hard Lemonade) (1 drink or shot)", "liq",
     "1 drink or shot", "vodka, gin, hard seltzer; White Claw, Truly Seltzer, Mikes Hard Lemonade", ""),
    ("Plain water, include bottled, sparkling, or tap (8 oz. cup)", "h2o", "8 oz. cup", "", "include bottled, sparkling, or tap"),
    ("Decaffeinated tea, exclude herbal (8 oz. cup)", "tea.decaf", "8 oz. cup", "", "exclude herbal"),
    ("Tea with caffeine, including green tea (8 oz. cup)", "tea", "8 oz. cup", "", "including green tea"),
    ("Decaffeinated coffee (8 oz. cup)", "decaf", "8 oz. cup", "", ""),
    ("Coffee with caffeine (8 oz. cup)", "coff", "8 oz. cup", "", ""),
    ("Dairy coffee drink (hot/cold), e.g., Cappuccino (12 oz.)", "coff.drink", "12 oz.", "Cappuccino", "hot/cold")]:
    food(3, S, lab, v, por, ex, instr, group=g)

S = "Sweets, Baked Goods, Miscellaneous"
add(4, "5", S, "Sweets, Baked Goods, Miscellaneous section passthru (P)", "passthru", "P", "spt")
food(4, S, "Milk chocolate (bar or pack), e.g., Hershey's, M&M's", "choc", "bar or pack", "Hershey's, M&M's")
food(4, S, "Dark chocolate, e.g., Hershey's Dark or Dove Dark", "choc.dark", examples="Hershey's Dark or Dove Dark", note="no portion printed")
food(4, S, "Candy bars, e.g., Snickers, Milky Way, Reese's", "candy.nuts", examples="Snickers, Milky Way, Reese's", note="no portion printed")
food(4, S, "Candy without chocolate (1 oz.)", "candy", "1 oz.")
g = "Cookies (1) or Brownies (1)"
food(4, S, "Ready made or from mix or dough", "coox.brn", "1", group=g)
food(4, S, "Home-baked, from scratch", "coox.brn.home", "1", group=g)
for lab, v, por, ex in [
    ("Doughnuts (1)", "donut", "1", ""),
    ("Cake, homemade or ready made (slice)", "cake.frost", "slice", ""),
    ("Pie, homemade or ready made (slice)", "pie.comm", "slice", ""),
    ("Jams, jellies, preserves, syrup, or honey (1 Tbs)", "jam", "1 Tbs", ""),
    ("Peanut butter or other nut butter (1 Tbs)", "p.bu", "1 Tbs", ""),
    ("Popcorn, regular, fat free or light (2–3 cups)", "popc", "2–3 cups", ""),
    ("Sweet roll, coffee cake or other pastry (1)", "s.roll.c", "1", ""),
    ("Snack bars, e.g., Kind, Kashi, granola (1)", "snack.bar", "1", "Kind, Kashi, granola"),
    ("Energy bars or high protein bars, e.g., Clif, Quest, RXbar", "energy.bar", "", "Clif, Quest, RXbar"),
    ("Diet nutrition drinks, e.g. Slimfast (1)", "diet.drk", "1", "Slimfast"),
    ("Ensure, Boost or other meal replacement drinks (1)", "meal.rpl.drk", "1", "Ensure, Boost"),
    ("Pretzels (1 small bag or serving)", "pretzel", "1 small bag or serving", ""),
    ("Peanuts (small packet or 1 oz.)", "nuts", "small packet or 1 oz.", ""),
    ("Walnuts (1 oz.)", "walnuts", "1 oz.", ""),
    ("Other nuts (small packet or 1 oz.)", "oth.nuts", "small packet or 1 oz.", ""),
    ("Dried cranberries (1/4 cup)", "dr.cranb", "1/4 cup", ""),
    ("Mixed dried fruit (1/4 cup)", "mix.dr.frt", "1/4 cup", ""),
    ("Oat bran, other bran (wheat, etc.), added to food (1 Tbs)", "oth.bran", "1 Tbs", "wheat"),
    ("Chowder or cream soup (1 cup)", "chowder", "1 cup", ""),
    ("Tomato soup (1 cup)", "tom.soup", "1 cup", ""),
    ("Ketchup or red chili sauce (1 Tbs)", "catsup", "1 Tbs", ""),
    ("Flaxseed (1 Tbs)", "flax", "1 Tbs", ""),
    ("Seeds, e.g., pumpkin, sunflower, etc. (1/4 cup)", "seeds", "1/4 cup", "pumpkin, sunflower"),
    ("Garlic, fresh or powdered (1 clove or 4 shakes)", "garlic2", "1 clove or 4 shakes", ""),
    ("Olives, any type (3)", "olives", "3", ""),
    ("Olive oil added to food or bread (1 Tbs)", "olive.oil", "1 Tbs", ""),
    ("Low-fat or olive oil mayonnaise (1 Tbs)", "mayo.d", "1 Tbs", ""),
    ("Regular mayonnaise (1 Tbs)", "mayo", "1 Tbs", "")]:
    note = "portion may be cut off at the column edge on this proof" if v == "energy.bar" else ""
    food(4, S, lab, v, por, ex, "added to food" if v == "oth.bran" else "", note=note)
food(4, S, "Salad dressing (1–2 Tbs): How often?", "o.v", "1–2 Tbs", group="Salad dressing (1–2 Tbs)")
add(4, "5", S, "Salad dressing: Type(s)", "multi_choice", "Nonfat|Low-fat|Olive oil|Regular (e.g., Italian, Ranch)",
    "dress.nofat|dress.lofat|dress.olive|dress.other", group="Salad dressing (1–2 Tbs)", passthru_var="dress.pt",
    note="each option is its own variable")
food(4, S, "Artificial sweeteners (1 packet): How often?", "artif.sweet", "1 packet", group="Artificial sweeteners (1 packet)")
add(4, "5", S, "Artificial sweeteners: Type(s)", "multi_choice", "Splenda|Equal|NutraSweet|Sweet'N Low|Truvia|Stevia",
    "as.sp|as.eq|as.ns|as.sl|as.tr|as.st", group="Artificial sweeteners (1 packet)", passthru_var="as.pt",
    note="each option is its own variable")

# ---------------- page 4: Q6-Q13 (variables in perls9.scn2) ----------------
LIVER = "Never|Less than 1/mo|1/mo|2–3/mo|1/week or more"
add(4, "6", "Liver", "Liver section passthru", "passthru", "P", "liver.pt")
add(4, "6", "Liver", "Liver: beef, calf or pork (4 oz.)", "single_choice", LIVER, "liver", portion="4 oz.")
add(4, "6", "Liver", "Liver: chicken or turkey (4 oz.)", "single_choice", LIVER, "chix.liver", portion="4 oz.")
WK = "Less than once a week|1–3 times per week|4–6 times per week|Daily"
FAT = "Real butter|Margarine|Olive oil|Vegetable oil|Veg. shortening|Lard|N/A"
add(4, "7", "Cooking", "How often do you eat pan-fried or sautéed food at home? (Exclude \"Pam\"-type spray)", "single_choice", WK, "ffh")
add(4, "8", "Cooking", "What kind of fat is most often used for pan-frying and sautéing at home? (Exclude \"Pam\"-type spray)",
    "single_choice", FAT, "fb|fm|foo|fvo|fsh|fl|fna", passthru_var="ffpt", note="each option is its own variable")
add(4, "9", "Cooking", "What kind of fat is most often used for baking COOKIES at home?",
    "single_choice", FAT, "bb|bm|boo|bvo|bsh|bl|bna", passthru_var="bapt", note="each option is its own variable")
add(4, "10", "Cooking", "What type of cooking oil is most often used at home? (e.g., Mazola Corn Oil) Specify brand and type",
    "text", "write-in")
add(4, "10", "Cooking", "Cooking oil code (coded bubbles next to Q10)", "multi_choice",
    "AVO (avocado)|OLV (olive)|BLE (blend)|PEA (peanut)|CAN (canola)|SAF (safflower)|COC (coconut)|SES (sesame)|"
    "COR (corn)|SUN (sunflower)|GRS (grapeseed)|WAL (walnut)|VEG (vegetable)",
    "avocado.oil|o|blend.oil|pn|rapeseed|sf|co|sesame|c|sn|grape|walnut|soy.90", passthru_var="oilpt",
    note="each code is its own variable; codes matched to the scn2 labels (e.g. CAN = rapeseed 'Canola', VEG = soy.90 'Vegetable')")
add(4, "11", "Eating out", "How often do you eat deep fried chicken, fish, shrimp, clams or onion rings away from home?",
    "single_choice", WK, "ffa")
add(4, "12", "Eating out", "How often do you eat toasted breads, bagel or English muffin (slice or 1 half bagel)?", "single_choice",
    WK + "|2+ times/day", "toast", portion="slice or 1 half bagel")
add(4, "13", "Diet", "Are you following any of these diets? (Mark all that apply.)", "multi_choice",
    "Low carb (Atkins, Paleo, etc.)|KETO|Vegan|Vegetarian|Gluten free|Low fat|Low sodium|Low calorie|Weight Watchers|"
    "Diabetic|Intermittent fasting|DASH|Mediterranean|Other|None",
    "diet.carb|diet.keto|diet.vegan|diet.veg|diet.gf|diet.fat|diet.na|diet.cal|diet.ww|diet.dm|diet.fast|diet.dash|diet.med|diet.oth|diet.none",
    passthru_var="dietpt", note="each option is its own variable")

cols = ["q_id", "page", "question_no", "section", "group_label", "item_label", "portion_text", "examples", "instruction",
        "response_type", "response_options", "var", "passthru_var", "data_file", "note"]

dicts = {k: read_dict(p) for k, p in DICTS.items()}
split = lambda x: [v for v in x.split("|") if v]
used = set()
for r in rows:
    vs = split(r["var"]) + split(r["passthru_var"])
    files = []
    for v in vs:
        f = next((k for k, d in dicts.items() if v in d and v != "id"), None)
        if f is None:
            raise SystemExit(f"{v!r} ({r['item_label']}) not found in any data dictionary")
        files.append(f)
        used.add(v)
    r["data_file"] = "|".join(sorted(set(files)))
    n_opt, n_var = len(r["response_options"].split("|")), len(split(r["var"]))
    if n_var > 1 and n_var != n_opt:
        raise SystemExit(f"{r['item_label']}: {n_opt} options but {n_var} variables")
for i, r in enumerate(rows, 1):
    r["q_id"] = f"Q{i:03d}"
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
print(f"wrote {OUT} ({len(rows)} rows)")
for k, d in dicts.items():
    unmatched = [v for v in d if v not in used]
    print(f"{k}: {len(d)} variables, not on the form: {unmatched}")
