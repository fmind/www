+++
title = "Happy Birthday XP: Celebrating Gemini Deep Think (and My Daughter’s 6th Birthday)"
description = "A father tests Gemini AI’s coding skills to create a magical birthday for his 6-year-old. See the staggering results from Deep Think!"
date = "2025-08-03"
tags = ["LLM", "Demo"]
slug = "happy-birthday-xp-celebrating-gemini-deep-think-and-my-daughters-6th-birthday"
syndicated = "https://medium.com/@fmind/happy-birthday-xp-celebrating-gemini-deep-think-and-my-daughters-6th-birthday-eca018c7cea0"
draft = false
+++

Birthdays are always milestones. But this year, my daughter Augustine’s 6th birthday coincided with another significant event: a staggering leap forward in AI capabilities: [the release of Gemini Deep Think](https://blog.google/products/gemini/gemini-2-5-deep-think/).

To celebrate, I decided to combine the two. I crafted a complex coding challenge and presented it to the three tiers of Google’s Gemini 2.5 models: Flash, Pro, and the powerful new Deep Think capability.

The goal was simple: Could AI create a genuinely magical, interactive experience for a six-year-old?

![Source: Gemini App](/static/img/articles/happy-birthday-xp-celebrating-gemini-deep-think-and-my-daughters-6th-birthday/cover.webp)

Source: Gemini App

The results were more than just a birthday gift; they were a clear demonstration of the accelerating pace of AI. As Simon Willison recently illustrated in his talk [“2025 in LLMs so far, illustrated by Pelicans on Bicycles,”](https://www.youtube.com/watch?v=YpY83-kA7Bo) we are seeing models make sudden, incredible leaps in capability. This experiment was a perfect example of that leap in action.

You can explore the results yourself on the [Happy Birthday XP](https://sites.google.com/fmind.dev/happy-birthday-xp/home) site or check out the full [YouTube Playlist here](https://www.youtube.com/playlist?list=PLPCnNL6Y2PbRZCXG2miPerG75T_1uj78E).

### The Challenge: The “Magical Birthday Adventure” Prompt

I didn’t ask for a simple webpage. I asked for a multi-scene, interactive experience, demanding coordination between animation, user interaction, and programmatically generated audio.

The major constraint: The entire experience had to be contained within a single HTML file (HTML, CSS, JS).

Here is a summary of the [prompt requirements](https://sites.google.com/fmind.dev/happy-birthday-xp/home):

- **Scene 1: The Enchanted Gift.** A twilight sky and a shimmering gift box that acts as a start button.
- **Scene 2: The Grand Unveiling.** The box opens, releasing particles that assemble to spell “Happy 6th Birthday, Augustine!”
- **Scene 3: A Sky Full of Joy.** A fireworks spectacle where the user can click to launch more fireworks. Simultaneously, balloons float up, which the user can pop for confetti and sound.
- **Scene 4: The Birthday Wish.** A cake with 6 candles slides in. The user clicks “Make a wish!” to blow them out.
- **Scene 5: The Grand Finale.** Confetti falls, the “Happy Birthday” song plays, and a final message appears.

This is a tough prompt. It requires understanding narrative flow, complex JavaScript interactions, CSS animation timing, and synthesizing audio.

![Source: https://developers.googleblog.com/en/start-building-with-gemini-25-flash/](/static/img/articles/happy-birthday-xp-celebrating-gemini-deep-think-and-my-daughters-6th-birthday/02.webp)

Source: [https://developers.googleblog.com/en/start-building-with-gemini-25-flash/](https://developers.googleblog.com/en/start-building-with-gemini-25-flash/)

Let’s see how the models did.

### Round 1: Gemini 2.5 Flash

[Gemini 2.5 Flash](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash?hl=fr) is designed for speed and efficiency. It’s great for basic tasks, but complex, creative coding is not its primary strength.

_Watch the Flash result:_ [_https://youtu.be/g6KLIY7hy-I_](https://youtu.be/g6KLIY7hy-I)

Flash grasped the very basics of the request, but not much more.

**The Good:**

- It created the initial scene: A blue background and a box labeled “Open Me!” (00:00).
- Clicking the box triggers a transition (00:03).
- The birthday message (“Happy 6th Birthday, Augustine!”) appears with a glow effect (00:06).

**The Bad:**

- The aesthetics are extremely basic — just a pink square on a blue background.
- It missed almost all the required interactivity and complexity.
- There are no fireworks, no balloons, no cake, and no multi-scene coordination.
- The transition is an abrupt fade to black.

**The Verdict:** Flash delivered a functional webpage, but the “magic” was missing. It followed the first two instructions and then essentially gave up.

### Round 2: Gemini 2.5 Pro

[Gemini 2.5 Pro](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-pro?hl=fr) is the workhorse model, balancing capability with performance. I expected an improvement over Flash, and I got one.

_Watch the Pro result:_ [_https://youtu.be/4t0Hm_zeGqc_](https://youtu.be/4t0Hm_zeGqc)

Pro provided a better aesthetic and a closer attempt at the prompt.

**The Good:**

- The visuals are much improved. The initial scene has a starry twilight background as requested (00:00).
- The text reveal has a nice neon glow effect (00:05).
- Crucially, it implemented a fireworks spectacle (00:10). The fireworks look good and are varied.

**The Bad:**

- The gift box CSS is slightly buggy (the lid is misplaced and the text is overlapping at the start 00:00).
- It completely missed the interactive balloon popping game.
- It skipped the entire birthday cake and candle sequence.
- It struggled with the text formatting, displaying “Happy6thBirthday,Augustine!”

**The Verdict:** A solid effort. It looks better and includes one of the major visual elements (the fireworks). However, it still failed to manage the complexity of the entire multi-stage request.

### The Ultimate Critic: A 6-Year-Old’s Review (Part 1)

I showed both the Flash and Pro versions to Augustine. She clicked the button, saw the text, watched the fireworks for a moment on the Pro version, and then looked at me and asked, “Is that it?”

![Source: Gemini App](/static/img/articles/happy-birthday-xp-celebrating-gemini-deep-think-and-my-daughters-6th-birthday/03.webp)

Source: Gemini App

Unmoved. The magic had failed to land.

### Round 3: Gemini DeepThink

Enter [Deep Think](https://blog.google/products/gemini/gemini-2-5-deep-think/). This represents the cutting edge of Gemini’s capabilities, utilizing advanced reasoning and complex instruction following. The difference was immediate and profound.

_Watch the DeepThink result:_ [_https://youtu.be/CA55UQ0tGrQ_](https://youtu.be/CA55UQ0tGrQ)

Deep Think didn’t just execute the instructions; it understood the _intent_ of creating a magical experience.

**The Execution:**

- **Scene Coordination:** The flow is seamless. The initial scene is polished, with a beautiful gift box and ribbon (00:00).
- **The Reveal:** When clicked, the box doesn’t just disappear; it bursts open with a flood of stars (00:03) before revealing the glowing birthday message (00:06).
- **The Interactive Game:** This is where DeepThink shines. Balloons begin to float up (00:13). Not only can you pop them, but the model implemented _playful, realistic balloon physics_. They bob, they float naturally, and they even bump into the text elements (00:25). They pop with satisfying confetti bursts and synthesized “pop” sound effects (00:14 onwards).
- **The Climax:** The balloons fade, and a stylized birthday cake with 6 lit candles glides in (01:07). The “Make a wish!” button appears (01:09).
- **The Finale:** Clicking the button blows out the candles with a distinct “whoosh” sound effect (01:12), triggering a synthesized “Happy Birthday” melody and the final, heartwarming message: “We love you! Have the most wonderful day!” (01:14).

**The Verdict:** Staggering. Deep Think nailed almost every aspect of the prompt. The attention to detail, the better sound design, the playful physics, and the timing of the animations were all far beyond what Flash and Pro could achieve.

### The Ultimate Critic: A 6-Year-Old’s Review (Part 2)

When I showed the DeepThink version to Augustine, her eyes lit up. She was captivated by the opening animation, and she _loved_ the balloon popping game. She giggled as they popped, delighted by the physics and the confetti.

The final message, telling her she would have a wonderful day, made her smile.

![Source: Gemini App](/static/img/articles/happy-birthday-xp-celebrating-gemini-deep-think-and-my-daughters-6th-birthday/04.webp)

Source: Gemini App

She immediately hit “Play Again!” and played through the entire experience four times in a row.

Mission accomplished. Magic delivered.

### The Staggering Progress and the Widening Gap

This simple birthday experiment highlights a critical trend in the current AI landscape. The difference between the models is not merely incremental; it is **exponential**.

A year ago, getting the result that Flash produced would have been notable. Today, it’s underwhelming. While Pro provided a competent result, Deep Think delivered a _delightful_ one.

It demonstrates that the frontier models are no longer just completing tasks; they are synthesizing complex requirements and producing results that feel creative and polished. The inclusion of realistic physics in a simple game, generated from a single prompt, is remarkable.

We are witnessing a rapidly widening gap in two areas:

1. **The gap between people using AI and those not.**
2. **The gap between people using powerful, frontier models (like Deep Think) and those using basic models for complex tasks (like Flash).**

The level of leverage that a model like Gemini Deep Think provides is astonishing. In minutes, it created an experience that would have taken a human developer significant time to code, debug, and polish.

As we celebrate Augustine’s 6th birthday, I’m also celebrating the arrival of this incredible technology. The progress is staggering, and I’m thrilled to have such power at my fingertips. The future of AI-assisted creation isn’t just coming; it’s already here.

![Source: https://blog.google/products/gemini/gemini-2-5-deep-think/](/static/img/articles/happy-birthday-xp-celebrating-gemini-deep-think-and-my-daughters-6th-birthday/05.webp)

Source: [https://blog.google/products/gemini/gemini-2-5-deep-think/](https://blog.google/products/gemini/gemini-2-5-deep-think/)
