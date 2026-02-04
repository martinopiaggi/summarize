"""Progress indicators for the summarizer package."""

import sys
import time
import threading
from typing import Optional


class ProgressSpinner:
    """A simple terminal spinner for indicating progress."""

    def __init__(self, message: str = "Processing", verbose: bool = False):
        self.message = message
        self.spinner_chars = "|/-\\"
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.verbose = verbose

    def start(self) -> None:
        """Start the spinner animation."""
        if not self.verbose:
            return
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()

    def stop(self) -> None:
        """Stop the spinner animation."""
        if not self.verbose:
            return
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")
        sys.stdout.flush()

    def _spin(self) -> None:
        """Internal method to animate the spinner."""
        i = 0
        while self.running:
            sys.stdout.write(
                f"\r{self.message}... {self.spinner_chars[i % len(self.spinner_chars)]}"
            )
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    def __enter__(self) -> "ProgressSpinner":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - always stops the spinner."""
        self.stop()


class ProgressBar:
    """A terminal progress bar for tracking completion."""

    def __init__(self, total: int, prefix: str = "Progress", length: int = 50):
        self.total = total
        self.prefix = prefix
        self.length = length
        self.current = 0

    def update(self, current: Optional[int] = None) -> None:
        """Update the progress bar."""
        if current is not None:
            self.current = current
        else:
            self.current += 1

        percent = (self.current / self.total) * 100
        filled_length = int(self.length * self.current // self.total)
        bar = "#" * filled_length + "-" * (self.length - filled_length)

        sys.stdout.write(
            f"\r{self.prefix}: |{bar}| {self.current}/{self.total} ({percent:.1f}%)"
        )

        sys.stdout.flush()

        if self.current >= self.total:
            print()  # New line when complete


class SimpleProgress:
    """A simple dot-based progress indicator for non-verbose mode."""

    def __init__(self, total: int, message: str = "Processing"):
        self.total = total
        self.message = message
        self.current = 0
        self.dots_shown = 0
        self.max_dots = 20

    def start(self) -> None:
        """Show the initial message."""
        sys.stdout.write(f"{self.message} ")
        sys.stdout.flush()

    def update(self, current: Optional[int] = None) -> None:
        """Update progress with a dot."""
        if current is not None:
            self.current = current
        else:
            self.current += 1

        # Show a dot every N% of progress
        dots_needed = int((self.current / self.total) * self.max_dots)
        while self.dots_shown < dots_needed:
            sys.stdout.write(".")
            sys.stdout.flush()
            self.dots_shown += 1

    def finish(self, success: bool = True) -> None:
        """Complete the progress line."""
        status = "done" if success else "failed"
        print(f" {status}")


def print_status(message: str, status: str = "INFO", verbose: bool = False) -> None:
    """
    Print a status message with appropriate formatting.

    Args:
        message: The message to print
        status: Status type (INFO, SUCCESS, ERROR, WARNING, PROCESSING)
        verbose: If False, only shows errors and final success
    """
    if not verbose:
        # Only show errors and final success in non-verbose mode
        if status in ["ERROR", "SUCCESS"]:
            status_symbols = {
                "SUCCESS": "[+]",
                "ERROR": "[-]",
            }
            symbol = status_symbols.get(status, "[*]")
            print(f"{symbol} {message}")
        return

    timestamp = time.strftime("%H:%M:%S")
    status_symbols = {
        "INFO": "[i]",
        "SUCCESS": "[+]",
        "ERROR": "[-]",
        "WARNING": "[!]",
        "PROCESSING": "[~]",
    }
    symbol = status_symbols.get(status, "[*]")
    print(f"[{timestamp}] {symbol} {message}")
