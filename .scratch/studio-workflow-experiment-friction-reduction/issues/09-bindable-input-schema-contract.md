# Bindable Input Schema Contract

Status: resolved
Type: grilling
Blocked by: none

## Question

What is the code-owned contract for a bindable input: its fixed canonical name, the ComfyUI node/widget binding it can target, the reusable Playground block it renders, its fixed integer/float/text/dropdown/model rules, whether it is available to experiments, and whether it is required or optional for each Workflow type?

## Answer

Bindable inputs are the code-owned heart of the wrapper. The catalog initially contains Prompt, Seed, Step count, CFG scale, Sampler, Model UNET, VAE, and CLIP. Output is also bound in workflow creation, but is a separate required result binding that feeds the right-side Output panel rather than a Playground input block. Names are canonical and fixed; users do not rename bindable inputs or underlying widgets.

The catalog is a dictionary that maps each bindable input to its coded Playground block and binding rule. Initial blocks are multiline prompt/text, integer, float, dropdown/set, and model picker. Integer and float rules are fixed in code: Seed is an integer that may be negative, while inputs such as Width and Height can use the same integer block with a non-negative rule. Users do not customize block parameters. A bindable input maps one-to-one to one exact ComfyUI node widget/field; grouped bindings are not part of this contract.

The workflow wizard lists only catalog inputs, suggests likely graph targets, and requires the user to bind the exact node widget or field. Graph inputs outside the catalog are ignored by the Studio wrapper. Supporting a future capability such as an Ideogram JSON builder adds a new catalog entry, coded block, binding rule, and experiment behavior without changing existing blocks.

For T2I, save and run require Prompt, Seed, Model UNET, VAE, CLIP, and Output binding. Step count, CFG scale, and Sampler are optional bindable inputs. Each future Workflow type supplies its own required and optional catalog entries. In Experiment mode, a bindable input can be an axis when it is common and compatible across the selected Workflows; Workflow-specific inputs remain settable in their hidden per-Workflow sections but cannot be axes. Workflow Settings allowed-options filters limit values without preventing axis selection.
