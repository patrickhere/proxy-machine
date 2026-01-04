---
title: 'offset_pdf.py'
weight: 5
---

It's pivotal to ensure that your card fronts and backs are aligned. The front and back alignment is mainly determined by your printer, but it's not always possible to calibrate it.

`offset_pdf.py` is a CLI tool that adds an offset to every other page in a PDF. This offset can compensate for the natural offset of your printer, allowing you to have good front and back alignment.

## Basic Usage

First, you must determine the offset by using the [calibration sheets](https://github.com/Alan-Cha/silhouette-card-maker/tree/main/calibration).

`<paper size>_calibration.pdf` has a front page and a back page.

![Calibration](/images/calibration.png)

The front page is a simple grid of squares.

The back page is the same grid of squares, except each square has a slight offset. The following grid illustrates the applied offsets.

```
| (-2, -2) | (-1, -2) | ( 0, -2) | ( 1, -2) | ( 2, -2) |
--------------------------------------------------------
| (-2, -1) | (-1, -1) | ( 0, -1) | ( 1, -1) | ( 2, -1) |
--------------------------------------------------------
| (-2,  0) | (-1,  0) |  Center  | ( 1,  0) | ( 2,  0) |
--------------------------------------------------------
| (-2,  1) | (-1,  1) | ( 0,  1) | ( 1,  1) | ( 2,  1) |
--------------------------------------------------------
| (-2,  2) | (-1,  2) | ( 0,  2) | ( 1,  2) | ( 2,  2) |
```

To determine the required offset, print out `<paper size>_calibration.pdf` with the card stock you plan to use.

Shine a strong light on the front so you can see the shadows on the back. Determine which set of front and back squares are aligned. This set will provide your offset.

Create and start your virtual Python environment and install Python dependencies if you have not done so already. See [here]({{% ref "create.md#basic-usage" %}}) for more information.

Run the script with your offset.
```sh
python offset_pdf.py --x_offset -5 --y_offset 10
```

Get your offset PDF at `game/output/game_offset.pdf`.

## Save Offset

You can save your `x` and `y` offset with the `--save` option. After saving your offset, it'll be automatically applied every time you run `offset_pdf.py`. You can override the loaded offset using `--x_offset` and `--y_offset`.

```sh
python offset_pdf.py --x_offset -5 --y_offset 10 --save
```

Additionally, you can automatically apply a saved offset in [`create_pdf.py`]({{% ref "create.md" %}}) by using the `--load_offset` option.

```sh
python create_pdf.py --load_offset
```

## CLI Options

```
Usage: offset_pdf.py [OPTIONS]

Options:
  --pdf_path TEXT         The path of the input PDF.
  --output_pdf_path TEXT  The desired path of the offset PDF.
  -x, --x_offset INTEGER  The desired offset in the x-axis.
  -y, --y_offset INTEGER  The desired offset in the y-axis.
  -s, --save              Save the x and y offset values.
  --ppi INTEGER RANGE     Pixels per inch (PPI) when creating PDF.  [default:
                          300; x>=0]
  --help                  Show this message and exit.
```
