"""A built-in lesson so the demo (and a first run without internet) has
something to teach. Original text written for this project."""

TOPIC = "spaced repetition"
TITLE = "Spaced repetition"
DESCRIPTION = "How S.A.M.U.E.L. schedules your flashcards"
TEXT = (
    "Spaced repetition is a study method in which material is reviewed at increasing intervals. "
    "It works because of the spacing effect, the finding that memories last longer when practice is spread out "
    "instead of crammed into one session. "
    "The psychologist Hermann Ebbinghaus described the forgetting curve in 1885, showing how quickly "
    "new information fades without review. "
    "Testing yourself, called retrieval practice, strengthens memory more than simply rereading notes. "
    "The SM-2 algorithm, published by Piotr Wozniak in 1987, gives every card an ease factor that starts at 2.5. "
    "After two successful reviews the next interval is the previous interval multiplied by the ease factor. "
    "A failed answer sends the card back to the beginning, so weak cards come back the next day."
)
