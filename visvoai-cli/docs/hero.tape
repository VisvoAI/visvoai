# VisvoAI CLI — hero recording. Regenerate: source ~/.zshrc && vhs hero.tape
# Real model (gemini-2.5-flash), real edits, unscripted agent behavior —
# only the typing is scripted. Stage /tmp/visvoai-demo (small git repo with
# taskly.py), ensure a clean tree, then: vhs hero.tape
Output hero.gif
Set FontSize 15
Set Width 1400
Set Height 850
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set Shell "zsh"

Hide
Type "cd /tmp/visvoai-demo && clear"
Enter
Sleep 1s
Show

Type "visvoai --model gemini:gemini-2.5-flash"
Enter
Sleep 5s

Type "add a --version flag to taskly.py that prints 'taskly 1.0' and exits"
Sleep 1s
Enter

# stream, then approve whenever a prompt appears (Enter on the empty
# input is a no-op) — tight cadence so waits never read as stalls
Sleep 12s
Enter
Sleep 3s
Enter
Sleep 3s
Enter
Sleep 3s
Enter
Sleep 3s
Enter
Sleep 3s
Enter
Sleep 3s
Enter
Sleep 3s
Enter
Sleep 3s
Enter
Sleep 10s

Screenshot hero_final.png
Sleep 3s
