# Eval Harness Feedback

**Run date:**
**Branch:** feature/phase-4-review-fixes
**Planner:** claude-sonnet-4-20250514
**Reviewer:** claude-opus-4-20250514

---

## Overall Impressions

_How did the plans look overall? Any patterns across personas?_

For pace zones, 'easy' isnt always that helpful, especially to the new runner, we could try doing things like 'zone 2' or zone 1 etc to show the heartrate stuff, also easy to give information about around hte plan and leave the plan more simplistic if that makes sense. The description si good, once again how are we getting teh TSS values> i am just curious to see that. 
All long runs are easy, even for a new runner it can be good to push yourself right? lets define that more, this ties in with the 80 20 rule you put in, where does that come from?
pace zone repitition? what does that even mean, lets maybe pre define these in prompting? we can discuss this.

Overall not a terrible first start? but a ton to workout before moving to more development past this phase. 


---

## Per-Persona Feedback

### beginner_runner (Sarah — 5K, conservative, 12km/week)

**Plan quality (1-5):**
**Safety (1-5):**
**Would you trust this for a real beginner?**

**Notes:**


---

### advanced_marathoner (Marcus — marathon, moderate, 100km/week)

**Plan quality (1-5):**
**Safety (1-5):**
**Does the periodization make sense for an experienced runner?**

**Notes:**


---

### aggressive_spiker (Jake — marathon, aggressive, 30km/week)

**Plan quality (1-5):**
**Safety (1-5):**
**Did the reviewer catch the dangerous progression from 30km to marathon?**

**Notes:**


---

### injury_prone_runner (Maria — 50K ultra, conservative, 65km/week)

**Plan quality (1-5):**
**Safety (1-5):**
**Does the plan respect injury history? Avoid aggravating movements?**

**Notes:**


---

### overtrained_athlete (Chris — half marathon, conservative, 80km/week)

**Plan quality (1-5):**
**Safety (1-5):**
**Does the plan recognize overtraining signals and prescribe recovery?**

**Notes:**


---

## Prompt Tuning Ideas

_Any suggestions for improving the planner or reviewer system prompts?_

need to take a look at prompts themsevles

For deterministic values, how are we getting those> not calculating but actually getting, are users uploading workouts and we are deriving form thaT? pretty much all but the most elite athletes wont know a lot of that stuff about themselves. 
Might need to investigate some stuff here

the safety rueles, like 80 easy 20 hard? where are we getting these from. 

For example, I have previous ankle injuries, but once I have worked the plan might only need to adjust some strengthening suggestions for me, but tarining I was totally fine with mileage increases at a normal rate. 

---

## Reviewer Quality

_Did the reviewer catch real issues? Were rejections justified? Any false positives/negatives?_

rejections were super easy, but sometimes the 'phrases' might actually be alrihgt? so investigate this. 

---

## Cost/Performance Notes

_Was the cost reasonable? Any personas take too many retries?_

The cost did seem a bit high, but I think thats because the plan needed a full rewrite all times, so not something to stress on a ton right now.


---

## Next Steps

_What should change before the next eval run?_

Need to do some investigation to prompts themsevles and then see what we can do to improve the process ourselves. 

