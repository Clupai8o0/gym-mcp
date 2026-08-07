import { MOVEMENTS } from "./art";
import { Illustration } from "./Illustration";
import sheet from "./MovementSheet.module.css";

/**
 * A contact sheet of six catalog movements, laid out in the same hairline cells the library grid
 * uses. It is the only place on the page where the "over eight hundred, illustrated, all one
 * style" claim is *shown* rather than asserted, which is why it sits in that band rather than
 * anywhere prettier.
 *
 * Six rather than one big figure, because the claim is *breadth*: a barbell row and a kettlebell
 * swing looking like they were drawn by the same hand is the whole point, and one drawing cannot
 * show that.
 *
 * The captions are real text, so the movement names are readable by a screen reader and a
 * crawler — the alternative, one image with six names in its alt string, is neither.
 *
 * Server component. No client JS; the entrances are CSS.
 */
export function MovementSheet() {
  return (
    <ul className={sheet.grid}>
      {MOVEMENTS.map((movement) => (
        <li key={movement.name} className={sheet.cell}>
          <Illustration art={movement} className={sheet.glyph} />
          <span className={sheet.caption}>{movement.label}</span>
        </li>
      ))}
    </ul>
  );
}
