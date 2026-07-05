import tkinter as tk

from app import ReminderApp


def main() -> None:
    root = tk.Tk()
    ReminderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
