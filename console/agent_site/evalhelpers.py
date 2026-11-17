"""Helpers available to the agent in every arm (identical across arms)."""


def show_png(path: str) -> None:
    """Display a PNG so Console returns it as an image (Console captures only pyplot figures)."""
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    img = mpimg.imread(path)
    h, w = img.shape[:2]
    dpi = 100
    fig = plt.figure(figsize=(w / dpi, h / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.axis("off")
    plt.show()
