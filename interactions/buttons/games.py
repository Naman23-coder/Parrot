from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass
from functools import partial, cached_property
from typing import Iterator, Literal, Optional, Union, overload

import discord
from discord import Member as User
from discord.ext import commands, boardgames
from random import sample, choice

from core import Cog, Parrot, Context

from discord.utils import MISSING
import akinator
from akinator.async_aki import Akinator
import emojis

BoardState = list[list[Optional[bool]]]


STATES = (
    "\N{REGIONAL INDICATOR SYMBOL LETTER X}",
    "\N{REGIONAL INDICATOR SYMBOL LETTER O}",
)

class Emojis:
    cross_mark = "\u274C"
    star = "\u2B50"
    christmas_tree = "\U0001F384"
    check = "\u2611"
    envelope = "\U0001F4E8"

    ok_hand = ":ok_hand:"
    hand_raised = "\U0001F64B"

  
    number_emojis = {
        1: "\u0031\ufe0f\u20e3",
        2: "\u0032\ufe0f\u20e3",
        3: "\u0033\ufe0f\u20e3",
        4: "\u0034\ufe0f\u20e3",
        5: "\u0035\ufe0f\u20e3",
        6: "\u0036\ufe0f\u20e3",
        7: "\u0037\ufe0f\u20e3",
        8: "\u0038\ufe0f\u20e3",
        9: "\u0039\ufe0f\u20e3"
    }

    confirmation = "\u2705"
    decline = "\u274c"
    incident_unactioned = "\N{NEGATIVE SQUARED CROSS MARK}"

    x = "\U0001f1fd"
    o = "\U0001f1f4"



NUMBERS = list(Emojis.number_emojis.values())
CROSS_EMOJI = Emojis.incident_unactioned

Coordinate = Optional[tuple[int, int]]
EMOJI_CHECK = Union[discord.Emoji, str]


class GameC4:
    """A Connect 4 Game."""

    def __init__(
        self,
        bot: Parrot,
        channel: discord.TextChannel,
        player1: discord.Member,
        player2: Optional[discord.Member],
        tokens: list[str],
        size: int = 7
    ):
        self.bot = bot
        self.channel = channel
        self.player1 = player1
        self.player2 = player2 or AI_C4(self.bot, game=self)
        self.tokens = tokens

        self.grid = self.generate_board(size)
        self.grid_size = size

        self.unicode_numbers = NUMBERS[:self.grid_size]

        self.message = None

        self.player_active = None
        self.player_inactive = None

    @staticmethod
    def generate_board(size: int) -> list[list[int]]:
        """Generate the connect 4 board."""
        return [[0 for _ in range(size)] for _ in range(size)]

    async def print_grid(self) -> None:
        """Formats and outputs the Connect Four grid to the channel."""
        title = (
            f"Connect 4: {self.player1.display_name}"
            f" VS {self.bot.user.display_name if isinstance(self.player2, AI_C4) else self.player2.display_name}"
        )

        rows = [" ".join(self.tokens[s] for s in row) for row in self.grid]
        first_row = " ".join(x for x in NUMBERS[:self.grid_size])
        formatted_grid = "\n".join([first_row] + rows)
        embed = discord.Embed(title=title, description=formatted_grid)

        if self.message:
            await self.message.edit(embed=embed)
        else:
            self.message = await self.channel.send(content="Loading...")
            for emoji in self.unicode_numbers:
                await self.message.add_reaction(emoji)
            await self.message.add_reaction(CROSS_EMOJI)
            await self.message.edit(content=None, embed=embed)

    async def game_over(self, action: str, player1: discord.user, player2: discord.user) -> None:
        """Announces to public chat."""
        if action == "win":
            await self.channel.send(f"Game Over! {player1.mention} won against {player2.mention}")
        elif action == "draw":
            await self.channel.send(f"Game Over! {player1.mention} {player2.mention} It's A Draw :tada:")
        elif action == "quit":
            await self.channel.send(f"{self.player1.mention} surrendered. Game over!")
        await self.print_grid()

    async def start_game(self) -> None:
        """Begins the game."""
        self.player_active, self.player_inactive = self.player1, self.player2

        while True:
            await self.print_grid()

            if isinstance(self.player_active, AI_C4):
                coords = self.player_active.play()
                if not coords:
                    await self.game_over(
                        "draw",
                        self.bot.user if isinstance(self.player_active, AI_C4) else self.player_active,
                        self.bot.user if isinstance(self.player_inactive, AI_C4) else self.player_inactive,
                    )
            else:
                coords = await self.player_turn()

            if not coords:
                return

            if self.check_win(coords, 1 if self.player_active == self.player1 else 2):
                await self.game_over(
                    "win",
                    self.bot.user if isinstance(self.player_active, AI_C4) else self.player_active,
                    self.bot.user if isinstance(self.player_inactive, AI_C4) else self.player_inactive,
                )
                return

            self.player_active, self.player_inactive = self.player_inactive, self.player_active

    def predicate(self, reaction: discord.Reaction, user: discord.Member) -> bool:
        """The predicate to check for the player's reaction."""
        return (
            reaction.message.id == self.message.id
            and user.id == self.player_active.id
            and str(reaction.emoji) in (*self.unicode_numbers, CROSS_EMOJI)
        )

    async def player_turn(self) -> Coordinate:
        """Initiate the player's turn."""
        message = await self.channel.send(
            f"{self.player_active.mention}, it's your turn! React with the column you want to place your token in."
        )
        player_num = 1 if self.player_active == self.player1 else 2
        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", check=self.predicate, timeout=30.0)
            except asyncio.TimeoutError:
                await self.channel.send(f"{self.player_active.mention}, you took too long. Game over!")
                return
            else:
                await message.delete()
                if str(reaction.emoji) == CROSS_EMOJI:
                    await self.game_over("quit", self.player_active, self.player_inactive)
                    return

                await self.message.remove_reaction(reaction, user)

                column_num = self.unicode_numbers.index(str(reaction.emoji))
                column = [row[column_num] for row in self.grid]

                for row_num, square in reversed(list(enumerate(column))):
                    if not square:
                        self.grid[row_num][column_num] = player_num
                        return row_num, column_num
                message = await self.channel.send(f"Column {column_num + 1} is full. Try again")

    def check_win(self, coords: Coordinate, player_num: int) -> bool:
        """Check that placing a counter here would cause the player to win."""
        vertical = [(-1, 0), (1, 0)]
        horizontal = [(0, 1), (0, -1)]
        forward_diag = [(-1, 1), (1, -1)]
        backward_diag = [(-1, -1), (1, 1)]
        axes = [vertical, horizontal, forward_diag, backward_diag]

        for axis in axes:
            counters_in_a_row = 1  # The initial counter that is compared to
            for (row_incr, column_incr) in axis:
                row, column = coords
                row += row_incr
                column += column_incr

                while 0 <= row < self.grid_size and 0 <= column < self.grid_size:
                    if self.grid[row][column] == player_num:
                        counters_in_a_row += 1
                        row += row_incr
                        column += column_incr
                    else:
                        break
            if counters_in_a_row >= 4:
                return True
        return False


class AI_C4:
    """The Computer Player for Single-Player games."""

    def __init__(self, bot: Parrot, game: GameC4):
        self.game = game
        self.mention = bot.user.mention

    def get_possible_places(self) -> list[Coordinate]:
        """Gets all the coordinates where the AI_C4 could possibly place a counter."""
        possible_coords = []
        for column_num in range(self.game.grid_size):
            column = [row[column_num] for row in self.game.grid]
            for row_num, square in reversed(list(enumerate(column))):
                if not square:
                    possible_coords.append((row_num, column_num))
                    break
        return possible_coords

    def check_ai_win(self, coord_list: list[Coordinate]) -> Optional[Coordinate]:
        """
        Check AI_C4 win.
        Check if placing a counter in any possible coordinate would cause the AI_C4 to win
        with 10% chance of not winning and returning None
        """
        if random.randint(1, 10) == 1:
            return
        for coords in coord_list:
            if self.game.check_win(coords, 2):
                return coords

    def check_player_win(self, coord_list: list[Coordinate]) -> Optional[Coordinate]:
        """
        Check Player win.
        Check if placing a counter in possible coordinates would stop the player
        from winning with 25% of not blocking them  and returning None.
        """
        if random.randint(1, 4) == 1:
            return
        for coords in coord_list:
            if self.game.check_win(coords, 1):
                return coords

    @staticmethod
    def random_coords(coord_list: list[Coordinate]) -> Coordinate:
        """Picks a random coordinate from the possible ones."""
        return random.choice(coord_list)

    def play(self) -> Union[Coordinate, bool]:
        """
        Plays for the AI_C4.
        Gets all possible coords, and determins the move:
        1. coords where it can win.
        2. coords where the player can win.
        3. Random coord
        The first possible value is choosen.
        """
        possible_coords = self.get_possible_places()

        if not possible_coords:
            return False

        coords = (
            self.check_ai_win(possible_coords)
            or self.check_player_win(possible_coords)
            or self.random_coords(possible_coords)
        )

        row, column = coords
        self.game.grid[row][column] = 2
        return coords

class Board:
    def __init__(
        self,
        state: BoardState,
        current_player: bool = False,
    ) -> None:
        self.state = state
        self.current_player = current_player
        self.winner: Optional[bool] = MISSING

    @property
    def legal_moves(self) -> Iterator[tuple[int, int]]:
        for c in range(3):
            for r in range(3):
                if self.state[r][c] is None:
                    yield (r, c)

    @cached_property
    def over(self) -> bool:

        # vertical
        for c in range(3):
            token = self.state[0][c]
            if token is None:
                continue
            if self.state[1][c] == token and self.state[2][c] == token:
                self.winner = token
                return True

        # horizontal
        for r in range(3):
            token = self.state[r][0]
            if token is None:
                continue
            if self.state[r][1] == token and self.state[r][2] == token:
                self.winner = token
                return True

        # descending diag
        if self.state[0][0] is not None:
            token = self.state[0][0]
            if self.state[1][1] == token and self.state[2][2] == token:
                self.winner = token
                return True

        # ascending diag
        if self.state[0][2] is not None:
            token = self.state[0][2]
            if self.state[1][1] == token and self.state[2][0] == token:
                self.winner = token
                return True

        # Check if board is empty
        for _ in self.legal_moves:
            break
        else:
            self.winner = None
            return True

        return False

    def move(self, r: int, c: int) -> Board:
        if (r, c) not in self.legal_moves:
            raise ValueError("Illegal Move")

        new_state = [[self.state[r][c] for c in range(3)] for r in range(3)]
        new_state[r][c] = self.current_player

        return Board(new_state, not self.current_player)

    @classmethod
    def new_game(cls) -> Board:
        state: BoardState = [[None for _ in range(3)] for _ in range(3)]
        return cls(state)


class AI:
    def __init__(self, player: bool) -> None:
        self.player = player

    def move(self, game: Board) -> Board:
        column = random.choice(tuple(game.legal_moves))
        return game.move(*column)


class NegamaxAI(AI):
    def __init__(self, player: bool) -> None:
        super().__init__(player)

    def heuristic(self, game: Board, sign: int) -> float:
        if sign == -1:
            player = not self.player
        else:
            player = self.player

        if game.over:
            if game.winner is None:
                return 0
            if game.winner == player:
                return 1_000_000
            return -1_000_000

        return random.randint(-10, 10)

    @overload
    def negamax(
        self,
        game: Board,
        depth: Literal[0] = ...,
        alpha: float = ...,
        beta: float = ...,
        sign: int = ...,
    ) -> tuple[int, int]:
        ...

    @overload
    def negamax(
        self,
        game: Board,
        depth: int = ...,
        alpha: float = ...,
        beta: float = ...,
        sign: int = ...,
    ) -> float:
        ...

    def negamax(
        self,
        game: Board,
        depth: int = 0,
        alpha: float = float("-inf"),
        beta: float = float("inf"),
        sign: int = 1,
    ) -> Union[float, tuple[int, int]]:
        if game.over:
            return sign * self.heuristic(game, sign)

        move = MISSING

        score = float("-inf")
        for c in game.legal_moves:
            move_score = -self.negamax(game.move(*c), depth + 1, -beta, -alpha, -sign)

            if move_score > score:
                score = move_score
                move = c

            alpha = max(alpha, score)
            if alpha >= beta:
                break

        if depth == 0:
            return move
        else:
            return score

    def move(self, game: Board) -> Board:
        return game.move(*self.negamax(game))


class ButtonTicTacToe(discord.ui.Button["GameTicTacToe"]):
    def __init__(self, r: int, c: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=c)
        self.r = r
        self.c = c

    def update(self):
        cell = self.view.board.state[self.r][self.c]

        if cell is not None or self.view.board.over:
            self.disabled = True

        if cell == True:
            self.style = discord.ButtonStyle.success
            self.label = "O"
        if cell == False:
            self.style = discord.ButtonStyle.danger
            self.label = "X"

    async def callback(self, interaction: discord.Interaction):

        self.view.board = self.view.board.move(self.r, self.c)
        self.view.update()

        if self.view.board.over:
            await self.view.game_over(interaction)
            return

        if self.view.current_player.bot:
            self.view.make_ai_move()
            self.view.update()

        if self.view.board.over:
            await self.view.game_over(interaction)
            return

        await interaction.response.edit_message(
            content=f"{self.view.current_player.mention}'s' ({STATES[self.view.board.current_player]}) turn!",
            view=self.view,
        )


class GameTicTacToe(discord.ui.View):
    children: list[ButtonTicTacToe]

    def __init__(self, players: tuple[User, User]):
        self.players = list(players)
        random.shuffle(self.players)

        super().__init__(timeout=None)
        self.board = Board.new_game()

        if self.current_player.bot:
            self.make_ai_move()

        for r in range(3):
            for c in range(3):
                self.add_item(ButtonTicTacToe(r, c))

        self.update()

    def update(self):
        for child in self.children:
            child.update()

    async def game_over(self, interaction: discord.Interaction):
        if self.board.winner is not None:
            content = f"{self.players[self.board.winner].mention} ({STATES[self.board.winner]}) wins!"
        else:
            content = "Draw!"

        for child in self.children:
            child.disabled = True  # type: ignore

        self.stop()
        return await interaction.response.edit_message(content=content, view=self)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user not in self.players:
            await interaction.response.send_message("Sorry, you are not playing", ephemeral=True)
            return False
        elif interaction.user != self.current_player:
            await interaction.response.send_message("Sorry, it is not your turn!", ephemeral=True)
            return False
        else:
            return True

    def make_ai_move(self):
        ai = NegamaxAI(self.board.current_player)
        self.board = ai.move(self.board)

    @property
    def current_player(self) -> User:
        return self.players[self.board.current_player]



@dataclass
class Square:
    """Each square on the battleship grid - if they contain a boat and if they've been aimed at."""

    boat: Optional[str]
    aimed: bool


Grid = list[list[Square]]
EmojiSet = dict[tuple[bool, bool], str]


@dataclass
class Player:
    """Each player in the game - their messages for the boards and their current grid."""

    user: Optional[discord.Member]
    board: Optional[discord.Message]
    opponent_board: discord.Message
    grid: Grid


CHOICES = ["rock", "paper", "scissors"]
SHORT_CHOICES = ["r", "p", "s"]

# Using a dictionary instead of conditions to check for the winner.
WINNER_DICT = {
    "r": {
        "r": 0,
        "p": -1,
        "s": 1,
    },
    "p": {
        "r": 1,
        "p": 0,
        "s": -1,
    },
    "s": {
        "r": -1,
        "p": 1,
        "s": 0,
    }
}

# The name of the ship and its size
SHIPS = {
    "Carrier": 5,
    "Battleship": 4,
    "Cruiser": 3,
    "Submarine": 3,
    "Destroyer": 2,
}


# For these two variables, the first boolean is whether the square is a ship (True) or not (False).
# The second boolean is whether the player has aimed for that square (True) or not (False)

# This is for the player's own board which shows the location of their own ships.
SHIP_EMOJIS = {
    (True, True): ":fire:",
    (True, False): ":ship:",
    (False, True): ":anger:",
    (False, False): ":ocean:",
}

# This is for the opposing player's board which only shows aimed locations.
HIDDEN_EMOJIS = {
    (True, True): ":red_circle:",
    (True, False): ":black_circle:",
    (False, True): ":white_circle:",
    (False, False): ":black_circle:",
}

# For the top row of the board
LETTERS = (
    ":stop_button::regional_indicator_a::regional_indicator_b::regional_indicator_c::regional_indicator_d:"
    ":regional_indicator_e::regional_indicator_f::regional_indicator_g::regional_indicator_h:"
    ":regional_indicator_i::regional_indicator_j:"
)

# For the first column of the board
NUMBERS = [
    ":one:",
    ":two:",
    ":three:",
    ":four:",
    ":five:",
    ":six:",
    ":seven:",
    ":eight:",
    ":nine:",
    ":keycap_ten:",
]

CROSS_EMOJI = "\u274e"
HAND_RAISED_EMOJI = "\U0001f64b"


class Colours:
    blue = 0x0279FD
    bright_green = 0x01D277
    dark_green = 0x1F8B4C
    orange = 0xE67E22
    pink = 0xCF84E0
    purple = 0xB734EB
    soft_green = 0x68C290
    soft_orange = 0xF9CB54
    soft_red = 0xCD6D6D
    yellow = 0xF9F586
    python_blue = 0x4B8BBE
    python_yellow = 0xFFD43B
    grass_green = 0x66FF00
    gold = 0xE6C200

    easter_like_colours = [
        (255, 247, 0),
        (255, 255, 224),
        (0, 255, 127),
        (189, 252, 201),
        (255, 192, 203),
        (255, 160, 122),
        (181, 115, 220),
        (221, 160, 221),
        (200, 162, 200),
        (238, 130, 238),
        (135, 206, 235),
        (0, 204, 204),
        (64, 224, 208),
    ]




class GameBattleShip:
    """A Battleship Game."""

    def __init__(
        self,
        bot: Parrot,
        channel: discord.TextChannel,
        player1: discord.Member,
        player2: discord.Member
    ):

        self.bot = bot
        self.public_channel = channel

        self.p1 = Player(player1, None, None, self.generate_grid())
        self.p2 = Player(player2, None, None, self.generate_grid())

        self.gameover: bool = False

        self.turn: Optional[discord.Member] = None
        self.next: Optional[discord.Member] = None

        self.match: Optional[re.Match] = None
        self.surrender: bool = False

        self.setup_grids()

    @staticmethod
    def generate_grid() -> Grid:
        """Generates a grid by instantiating the Squares."""
        return [[Square(None, False) for _ in range(10)] for _ in range(10)]

    @staticmethod
    def format_grid(player: Player, emojiset: EmojiSet) -> str:
        """
        Gets and formats the grid as a list into a string to be output to the DM.
        Also adds the Letter and Number indexes.
        """
        grid = [
            [emojiset[bool(square.boat), square.aimed] for square in row]
            for row in player.grid
        ]

        rows = ["".join([number] + row) for number, row in zip(NUMBERS, grid)]
        return "\n".join([LETTERS] + rows)

    @staticmethod
    def get_square(grid: Grid, square: str) -> Square:
        """Grabs a square from a grid with an inputted key."""
        index = ord(square[0].upper()) - ord("A")
        number = int(square[1:])

        return grid[number-1][index]  # -1 since lists are indexed from 0

    async def game_over(
        self,
        *,
        winner: discord.Member,
        loser: discord.Member
    ) -> None:
        """Removes games from list of current games and announces to public chat."""
        await self.public_channel.send(f"Game Over! {winner.mention} won against {loser.mention}")

        for player in (self.p1, self.p2):
            grid = self.format_grid(player, SHIP_EMOJIS)
            await self.public_channel.send(f"{player.user}'s Board:\n{grid}")

    @staticmethod
    def check_sink(grid: Grid, boat: str) -> bool:
        """Checks if all squares containing a given boat have sunk."""
        return all(square.aimed for row in grid for square in row if square.boat == boat)

    @staticmethod
    def check_gameover(grid: Grid) -> bool:
        """Checks if all boats have been sunk."""
        return all(square.aimed for row in grid for square in row if square.boat)

    def setup_grids(self) -> None:
        """Places the boats on the grids to initialise the game."""
        for player in (self.p1, self.p2):
            for name, size in SHIPS.items():
                while True:  # Repeats if about to overwrite another boat
                    ship_collision = False
                    coords = []

                    coord1 = random.randint(0, 9)
                    coord2 = random.randint(0, 10 - size)

                    if random.choice((True, False)):  # Vertical or Horizontal
                        x, y = coord1, coord2
                        xincr, yincr = 0, 1
                    else:
                        x, y = coord2, coord1
                        xincr, yincr = 1, 0

                    for i in range(size):
                        new_x = x + (xincr * i)
                        new_y = y + (yincr * i)
                        if player.grid[new_x][new_y].boat:  # Check if there's already a boat
                            ship_collision = True
                            break
                        coords.append((new_x, new_y))
                    if not ship_collision:  # If not overwriting any other boat spaces, break loop
                        break

                for x, y in coords:
                    player.grid[x][y].boat = name

    async def print_grids(self) -> None:
        """Prints grids to the DM channels."""
        # Convert squares into Emoji

        boards = [
            self.format_grid(player, emojiset)
            for emojiset in (HIDDEN_EMOJIS, SHIP_EMOJIS)
            for player in (self.p1, self.p2)
        ]

        locations = (
            (self.p2, "opponent_board"), (self.p1, "opponent_board"),
            (self.p1, "board"), (self.p2, "board")
        )

        for board, location in zip(boards, locations):
            player, attr = location
            if getattr(player, attr):
                await getattr(player, attr).edit(content=board)
            else:
                setattr(player, attr, await player.user.send(board))

    def predicate(self, message: discord.Message) -> bool:
        """Predicate checking the message typed for each turn."""
        if message.author == self.turn.user and message.channel == self.turn.user.dm_channel:
            if message.content.lower() == "surrender":
                self.surrender = True
                return True
            self.match = re.fullmatch("([A-J]|[a-j]) ?((10)|[1-9])", message.content.strip())
            if not self.match:
                self.bot.loop.create_task(message.add_reaction(CROSS_EMOJI))
            return bool(self.match)

    async def take_turn(self) -> Optional[Square]:
        """Lets the player who's turn it is choose a square."""
        square = None
        turn_message = await self.turn.user.send(
            "It's your turn! Type the square you want to fire at. Format it like this: A1\n"
            "Type `surrender` to give up."
        )
        await self.next.user.send("Their turn", delete_after=3.0)
        while True:
            try:
                await self.bot.wait_for("message", check=self.predicate, timeout=60.0)
            except asyncio.TimeoutError:
                await self.turn.user.send("You took too long. Game over!")
                await self.next.user.send(f"{self.turn.user} took too long. Game over!")
                await self.public_channel.send(
                    f"Game over! {self.turn.user.mention} timed out so {self.next.user.mention} wins!"
                )
                self.gameover = True
                break
            else:
                if self.surrender:
                    await self.next.user.send(f"{self.turn.user} surrendered. Game over!")
                    await self.public_channel.send(
                        f"Game over! {self.turn.user.mention} surrendered to {self.next.user.mention}!"
                    )
                    self.gameover = True
                    break
                square = self.get_square(self.next.grid, self.match.string)
                if square.aimed:
                    await self.turn.user.send("You've already aimed at this square!", delete_after=3.0)
                else:
                    break
        await turn_message.delete()
        return square

    async def hit(self, square: Square, alert_messages: list[discord.Message]) -> None:
        """Occurs when a player successfully aims for a ship."""
        await self.turn.user.send("Hit!", delete_after=3.0)
        alert_messages.append(await self.next.user.send("Hit!"))
        if self.check_sink(self.next.grid, square.boat):
            await self.turn.user.send(f"You've sunk their {square.boat} ship!", delete_after=3.0)
            alert_messages.append(await self.next.user.send(f"Oh no! Your {square.boat} ship sunk!"))
            if self.check_gameover(self.next.grid):
                await self.turn.user.send("You win!")
                await self.next.user.send("You lose!")
                self.gameover = True
                await self.game_over(winner=self.turn.user, loser=self.next.user)

    async def start_game(self) -> None:
        """Begins the game."""
        await self.p1.user.send(f"You're playing battleship with {self.p2.user}.")
        await self.p2.user.send(f"You're playing battleship with {self.p1.user}.")

        alert_messages = []

        self.turn = self.p1
        self.next = self.p2

        while True:
            await self.print_grids()

            if self.gameover:
                return

            square = await self.take_turn()
            if not square:
                return
            square.aimed = True

            for message in alert_messages:
                await message.delete()

            alert_messages = []
            alert_messages.append(await self.next.user.send(f"{self.turn.user} aimed at {self.match.string}!"))

            if square.boat:
                await self.hit(square, alert_messages)
                if self.gameover:
                    return
            else:
                await self.turn.user.send("Miss!", delete_after=3.0)
                alert_messages.append(await self.next.user.send("Miss!"))

            self.turn, self.next = self.next, self.turn



class Cell:
    def __init__(self, board, y: int, x: int):
        self.board = board
        self.y = y
        self.x = x
        self.mine = False
        self.clicked = False
        self.flagged = False

    @property
    def number(self):
        count = 0
        for y in range(self.y - 1, self.y + 2):
            for x in range(self.x - 1, self.x + 2):
                if 0 <= y < self.board.size_y and 0 <= x < self.board.size_x and self.board[x, y].mine:
                    count += 1
        return count

    def __str__(self):
        if self.clicked:

            if self.number == 0:
                number = "\u200b"
            else:
                number = boardgames.keycap_digit(self.number)

            return "💥" if self.mine else number
        else:
            return "🚩" if self.flagged else "⬜"


class Game(boardgames.Board[Cell]):
    def __init__(self, size_x=10, size_y=7):
        super().__init__(size_x, size_y)
        self.record = None
        self.last_state = None

        self._state = [[Cell(self, y, x) for x in range(self.size_x)] for y in range(self.size_y)]

    def setup(self, click_y: int, click_x: int):
        """Places mines on the board"""
        cells = [(i // self.size_x, i % self.size_x) for i in range(self.size_x * self.size_y)]
        cells.remove((click_y, click_x))

        for y, x in sample(cells, int((self.size_x * self.size_y + 1) // ((self.size_x * self.size_y) ** 0.5))):
            self[x, y].mine = True

    @property
    def num_mines(self) -> int:
        """Returns the number of mines"""
        count = 0
        for row in self:
            for cell in row:
                if cell.mine:
                    count += 1
        return count

    @property
    def num_flags(self) -> int:
        """Returns the currently placed number of flags"""
        count = 0
        for row in self:
            for cell in row:
                if cell.flagged:
                    count += 1
        return count

    @property
    def lost(self) -> bool:
        """Returns wether the game was lost or not."""
        for row in self:
            for cell in row:
                if cell.mine and cell.clicked:
                    return True
        return False

    @property
    def solved(self) -> bool:
        """Returns wether the board has been solved"""
        count = 0
        for row in self:
            for cell in row:
                if cell.clicked:
                    count += 1
        return count >= self.size_y * self.size_x - self.num_mines

    def click(self, y: int, x: int):
        """Clicks on a cell"""
        if self.size_x < x or self.size_y < y:
            raise commands.BadArgument("Cell out side the board.")

        cell = self[x, y]

        if not self.num_mines:
            self.setup(y, x)

        if cell.flagged:
            raise commands.BadArgument("You cannot click on a flagged cell.")

        cell.clicked = True

    def flag(self, y: int, x: int):
        """Flags a cell"""
        if self.size_x < x or self.size_y < y:
            raise commands.BadArgument("Cell out side the board.")

        cell = self[x, y]

        if cell.clicked:
            raise commands.BadArgument("You cannot flag a revealed cell.")

        cell.flagged = not cell.flagged

    def clean(self):
        """Cleans up the board state"""
        for y, row in enumerate(self):
            for x, cell in enumerate(row):
                if cell.clicked and not cell.number:
                    for i in range(y - 1, y + 2):
                        for j in range(x - 1, x + 2):
                            if 0 <= i < self.size_y and 0 <= j < self.size_x and not self[j, i].clicked:
                                self[j, i].flagged = False
                                self[j, i].clicked = True
                                self.clean()


class Button(discord.ui.Button["GameUI"]):
    def __init__(self, x: int, y: int, offset: int):
        self.x = x
        self.y = y
        self.offset = offset
        super().__init__(style=discord.ButtonStyle.blurple, label="\u200b", row=y)

    @property
    def cell(self):
        return self.view.meta.board[self.x, self.y + self.offset]

    def reveal(self):
        self.disabled = True
        self.style = discord.ButtonStyle.secondary
        self.label = str(self.cell)

        if self.cell.mine:
            self.style = discord.ButtonStyle.danger
        elif self.cell.flagged:
            self.style = discord.ButtonStyle.success
        elif self.cell.clicked:
            self.label = str(self.cell.number or "\u200b")

    def click(self):
        self.view.meta.board.click(self.y + self.offset, self.x)
        self.view.meta.board.clean()

        for view in self.view.meta.views:
            for child in view.children:
                if child.cell.clicked:
                    child.reveal()

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.click()
        await self.view.meta.update()


class GameUI(discord.ui.View):
    children: list[Button]

    def __init__(self, meta: MetaGameUI, offset: int):
        self.meta = meta
        self.offset = offset
        self.message = discord.utils.MISSING

        super().__init__(timeout=None)

        for r in range(5):
            for c in range(5):
                self.add_item(Button(r, c, offset))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.meta.player:
            await interaction.response.send_message("Sorry, you are not playing", ephemeral=True)
            return False
        return True

    async def update(self):
        if self.offset != 0:
            content = "\u200b"
        else:
            if self.meta.board.lost:
                content = "💥"
            elif self.meta.board.solved:
                content = ":tada:"
            else:
                content = "Minesweeper!"
        await self.message.edit(content=content, view=self)


class MetaGameUI:
    def __init__(self, player: discord.Member, channel: discord.TextChannel, size: int = 2):
        self.player = player
        self.channel = channel

        self.board = Game(5, size * 5)
        self.views = [GameUI(self, i * 5) for i in range(size)]

    async def update(self):
        if self.board.lost or self.board.solved:
            for view in self.views:
                for child in view.children:
                    child.disabled = True
                view.stop()

        for view in self.views:
            await view.update()

    async def start(self):
        for view in self.views:
            view.message = await self.channel.send(content="Minesweeper" if view.offset == 0 else "\u200b", view=view)


def is_no_game(ctx: Context):
    if ctx.channel in ctx.cog._games:
        raise commands.CheckFailure("There is already a Minesweeper game running.")
    return True


def is_game(ctx: Context):
    try:
        is_no_game(ctx)
    except commands.CheckFailure:
        return True
    raise commands.CheckFailure("No Connect Four game is running.")


class Games(Cog):
    """Play the classic Games!"""

    def __init__(self, bot: Parrot):
        self.bot = bot
        self.games: list[Game] = []
        self.waiting: list[discord.Member] = []
        self._games: dict[discord.TextChannel, Game] = {}
        self.games_c4: list[GameC4] = []
        self.waiting_c4: list[discord.Member] = []

        self.tokens = [":white_circle:", ":blue_circle:", ":red_circle:"]

        self.max_board_size = 9
        self.min_board_size = 5

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name='\N{VIDEO GAME}')
    
    def predicate(
        self,
        ctx: commands.Context,
        announcement: discord.Message,
        reaction: discord.Reaction,
        user: discord.Member
    ) -> bool:
        """Predicate checking the criteria for the announcement message."""
        if self.already_playing(ctx.author):  # If they've joined a game since requesting a player 2
            return True  # Is dealt with later on
        if (
            user.id not in (ctx.me.id, ctx.author.id)
            and str(reaction.emoji) == HAND_RAISED_EMOJI
            and reaction.message.id == announcement.id
        ):
            if self.already_playing(user):
                self.bot.loop.create_task(ctx.send(f"{user.mention} You're already playing a game!"))
                self.bot.loop.create_task(announcement.remove_reaction(reaction, user))
                return False

            if user in self.waiting:
                self.bot.loop.create_task(ctx.send(
                    f"{user.mention} Please cancel your game first before joining another one."
                ))
                self.bot.loop.create_task(announcement.remove_reaction(reaction, user))
                return False

            return True

        if (
            user.id == ctx.author.id
            and str(reaction.emoji) == CROSS_EMOJI
            and reaction.message.id == announcement.id
        ):
            return True
        return False

    def already_playing(self, player: discord.Member) -> bool:
        """Check if someone is already in a game."""
        return any(player in (game.p1.user, game.p2.user) for game in self.games)

    async def _get_opponent(self, ctx: Context) -> Optional[discord.Member]:
        message = await ctx.channel.send(
            embed=discord.Embed(description=f"{ctx.author.mention} wants to play Tic-Tac-Toe.").set_footer(
                text="react with \N{WHITE HEAVY CHECK MARK} to accept the challenge."
            )
        )
        await message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

        def check(reaction, user):
            if reaction.emoji != "\N{WHITE HEAVY CHECK MARK}":
                return False
            if user.bot:
                return False
            if user == ctx.author: 
                return False
            return True

        try:
            _, opponent = await self.bot.wait_for("reaction_add", check=check, timeout=60)
            return opponent
        except asyncio.TimeoutError:
            pass
        finally:
            await message.delete()
        return None
    
    async def check_author(self, ctx: commands.Context, board_size: int) -> bool:
        """Check if the requester is free and the board size is correct."""
        if self.already_playing_cf(ctx.author):
            await ctx.send("You're already playing a game!")
            return False

        if ctx.author in self.waiting_c4:
            await ctx.send("You've already sent out a request for a player 2")
            return False

        if not self.min_board_size <= board_size <= self.max_board_size:
            await ctx.send(
                f"{board_size} is not a valid board size. A valid board size is "
                f"between `{self.min_board_size}` and `{self.max_board_size}`."
            )
            return False

        return True

    def get_player(
        self,
        ctx: commands.Context,
        announcement: discord.Message,
        reaction: discord.Reaction,
        user: discord.Member
    ) -> bool:
        """Predicate checking the criteria for the announcement message."""
        if self.already_playing_cf(ctx.author):  # If they've joined a game since requesting a player 2
            return True  # Is dealt with later on

        if (
            user.id not in (ctx.me.id, ctx.author.id)
            and str(reaction.emoji) == Emojis.hand_raised
            and reaction.message.id == announcement.id
        ):
            if self.already_playing_cf(user):
                self.bot.loop.create_task(ctx.send(f"{user.mention} You're already playing a game!"))
                self.bot.loop.create_task(announcement.remove_reaction(reaction, user))
                return False

            if user in self.waiting_c4:
                self.bot.loop.create_task(ctx.send(
                    f"{user.mention} Please cancel your game first before joining another one."
                ))
                self.bot.loop.create_task(announcement.remove_reaction(reaction, user))
                return False

            return True

        if (
            user.id == ctx.author.id
            and str(reaction.emoji) == CROSS_EMOJI
            and reaction.message.id == announcement.id
        ):
            return True
        return False

    def already_playing_cf(self, player: discord.Member) -> bool:
        """Check if someone is already in a game."""
        return any(player in (game.player1, game.player2) for game in self.games_c4)

    @staticmethod
    def check_emojis(
        e1: EMOJI_CHECK, e2: EMOJI_CHECK
    ) -> tuple[bool, Optional[str]]:
        """Validate the emojis, the user put."""
        if isinstance(e1, str) and emojis.count(e1) != 1:
            return False, e1
        if isinstance(e2, str) and emojis.count(e2) != 1:
            return False, e2
        return True, None

    async def _play_game(
        self,
        ctx: commands.Context,
        user: Optional[discord.Member],
        board_size: int,
        emoji1: str,
        emoji2: str
    ) -> None:
        """Helper for playing a game of connect four."""
        self.tokens = [":white_circle:", str(emoji1), str(emoji2)]
        game = None  # if game fails to intialize in try...except

        try:
            game = GameC4(self.bot, ctx.channel, ctx.author, user, self.tokens, size=board_size)
            self.games_c4.append(game)
            await game.start_game()
            self.games_c4.remove(game)
        except Exception:
            # End the game in the event of an unforeseen error so the players aren't stuck in a game
            await ctx.send(f"{ctx.author.mention} {user.mention if user else ''} An error occurred. Game failed.")
            if game in self.games_c4:
                self.games_c4.remove(game)
            raise

    @commands.group(
        invoke_without_command=True,
        aliases=("4inarow", "connect4", "connectfour", "c4"),
        case_insensitive=True
    )
    async def connect_four(
        self,
        ctx: commands.Context,
        board_size: int = 7,
        emoji1: EMOJI_CHECK = "\U0001f535",
        emoji2: EMOJI_CHECK = "\U0001f534"
    ) -> None:
        """
        Play the classic game of Connect Four with someone!
        Sets up a message waiting for someone else to react and play along.
        The game will start once someone has reacted.
        All inputs will be through reactions.
        """
        check, emoji = self.check_emojis(emoji1, emoji2)
        if not check:
            raise commands.EmojiNotFound(emoji)

        check_author_result = await self.check_author(ctx, board_size)
        if not check_author_result:
            return

        announcement = await ctx.send(
            "**Connect Four**: A new game is about to start!\n"
            f"Press {Emojis.hand_raised} to play against {ctx.author.mention}!\n"
            f"(Cancel the game with {CROSS_EMOJI}.)"
        )
        self.waiting_c4.append(ctx.author)
        await announcement.add_reaction(Emojis.hand_raised)
        await announcement.add_reaction(CROSS_EMOJI)

        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add",
                check=partial(self.get_player, ctx, announcement),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            self.waiting_c4.remove(ctx.author)
            await announcement.delete()
            await ctx.send(
                f"{ctx.author.mention} Seems like there's no one here to play. "
                f"Use `{ctx.prefix}{ctx.invoked_with} ai` to play against a computer."
            )
            return

        if str(reaction.emoji) == CROSS_EMOJI:
            self.waiting_c4.remove(ctx.author)
            await announcement.delete()
            await ctx.send(f"{ctx.author.mention} Game cancelled.")
            return

        await announcement.delete()
        self.waiting_c4.remove(ctx.author)
        if self.already_playing_cf(ctx.author):
            return

        await self._play_game(ctx, user, board_size, str(emoji1), str(emoji2))

    @connect_four.command(aliases=("bot", "computer", "cpu"))
    async def ai(
        self,
        ctx: commands.Context,
        board_size: int = 7,
        emoji1: EMOJI_CHECK = "\U0001f535",
        emoji2: EMOJI_CHECK = "\U0001f534"
    ) -> None:
        """Play Connect Four against a computer player."""
        check, emoji = self.check_emojis(emoji1, emoji2)
        if not check:
            raise commands.EmojiNotFound(emoji)

        check_author_result = await self.check_author(ctx, board_size)
        if not check_author_result:
            return

        await self._play_game(ctx, None, board_size, str(emoji1), str(emoji2))

    @commands.command(aliases=['akinator'])
    @commands.bot_has_permissions(embed_links=True)
    async def aki(self, ctx: Context):
        """Answer the questions and let the bot guess your character!"""
        aki = Akinator()
        q = await aki.start_game()
        question_num = 1
        while aki.progression <= 80:
            question = q + "\n\t"
            embed = discord.Embed(color=0xFF0000)
            embed.add_field(
                name=f"Q-{question_num}\n{question}",
                value="Reply with `yes/y` | `no/n` | `i/idk/i don't know` | `p/probably` | `proably not/pn`",
            )
            await ctx.send(embed=embed)

            def check(m):
                replies = ("yes", "y", "no", "n", "i", "idk", "i don't know", "probably", "p", "probably not", "pn")
                return (m.content.lower() in replies and m.channel == ctx.channel and m.author == ctx.author)
            try:
              msg = await self.bot.wait_for("message", check=check, timeout=30)
            except Exception:
              return await ctx.send(f"{ctx.author.mention} you didn't answer on time")
            if msg.content.lower() in ("b", "back"):
                try:
                    q = await aki.back()
                except akinator.CantGoBackAnyFurther:
                    pass
            else:
                q = await aki.answer(msg.content)
            question_num += 1
        await aki.win()

        embed = discord.Embed(
            title=
            f"It's {aki.first_guess['name']} ({aki.first_guess['description']})! Was I correct?\n\t",
            color=0xFF0000,
        )
        embed.set_image(url=f"{aki.first_guess['absolute_picture_path']}")
        embed.add_field(name="Reply with `yes/y` `no/n`", value="\u200b")
        await ctx.send(embed=embed)

        def check(m):
            return (m.content.lower() in ("yes", "y", "no", "n") and m.channel == ctx.channel and m.author == ctx.author)

        try: 
            correct = await self.bot.wait_for("message", check=check, timeout=30)
        except Exception: 
            return await ctx.send(f"{ctx.author.mention} you didn't answer on time")
        if correct.content.lower() == "yes" or correct.content.lower() == "y":
            embed = discord.Embed(title="Yay! I guessed it right", color=0xFF0000)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="Oof! Kinda hard one", color=0xFF0000)
            await ctx.send(embed=embed)
    
    @commands.command(aliases=["tic", "tic_tac_toe"])
    async def tictactoe(self, ctx: Context, *, opponent: Optional[discord.Member] = None):
        """Start a Tic-Tac-Toe game!
        `opponent`: Another member of the server to play against. If not is set an open challenge is started.
        """

        if opponent is None:
            opponent = await self._get_opponent(ctx)
        else:
            if opponent == ctx.author:
                raise commands.BadArgument("You cannot play against yourself.")
            if not opponent.bot:
                if not await ctx.confirm(
                    self.bot,
                    ctx.channel,
                    opponent,
                    f"{opponent.mention}, {ctx.author} has challenged you to Tic-Tac-Toe! do you accept?",
                ):
                    opponent = None

        # If challenge timed out
        if opponent is None:
            raise commands.BadArgument("Challenge cancelled.")

        game = GameTicTacToe((ctx.author, opponent))

        await ctx.send(f"{game.current_player.mention}'s (X) turn!", view=game)  # type: ignore

    @commands.group(name="minesweeper", aliases=["ms"], invoke_without_command=True)
    async def minesweeper(self, ctx):
        """Minesweeper game commands"""
        pass

    @minesweeper.group(name="start")
    @commands.check(is_no_game)
    # @commands.check(is_war_channel)
    async def ms_start(self, ctx):
        """Starts a Minesweeper game"""
        if ctx.invoked_subcommand is None:
            await MetaGameUI(ctx.author, ctx.channel).start()

    @ms_start.command(name="tiny")
    async def ms_start_tiny(self, ctx):
        """Starts a easy difficulty Minesweeper game"""
        game = self._games[ctx.channel] = Game(5, 5)
        game.last_state = await ctx.send(
            f"Minesweeper Game Started!\n>>> {game}\n\nReveal cells with `{ctx.prefix}ms click`."
        )

    @ms_start.command(name="easy")
    async def ms_start_easy(self, ctx):
        """Starts a easy difficulty Minesweeper game"""
        game = self._games[ctx.channel] = Game(10, 7)
        game.last_state = await ctx.send(
            f"Minesweeper Game Started!\n>>> {game}\n\nReveal cells with `{ctx.prefix}ms click`."
        )

    @ms_start.command(name="medium")
    async def ms_start_medium(self, ctx):
        """Starts a medium difficulty Minesweeper game"""
        game = self._games[ctx.channel] = Game(17, 8)
        game.last_state = await ctx.send(
            f"Minesweeper Game Started!\n>>> {game}\n\nReveal cells with `{ctx.prefix}ms click`."
        )

    # @ms_start.command(name='hard')
    # async def ms_start_hard(self, ctx):
    #     """Starts a hard difficulty Minesweeper game"""
    #     game = self._games[ctx.channel] = Game(26, 10)
    #     game.last_state = await ctx.send(f'Minesweeper Game Started!\n>>> {game}\n\nReveal cells with `{ctx.prefix}ms click`.')

    @minesweeper.command(name="click")
    @commands.check(is_game)
    async def ms_click(self, ctx: Context, cells: commands.Greedy[boardgames.Cell]):
        """Clicks a cell on the board.
        cells are referenced by column then row for example `A2`"""

        game = self._games[ctx.channel]

        for cell in cells:
            game.click(*cell)

        game.clean()

        message = ""
        if game.lost:
            message += "\nToo bad, you lose."
        elif game.solved:
            message += "\nCongratulations, you win! :tada:"

        if game.last_state is not None:
            try:
                await game.last_state.delete()
            except Exception:
                pass
        game.last_state = await ctx.send(f">>> {game}" + message)

        # If game over delete the game.
        if game.lost or game.solved:
            del self._games[ctx.channel]

    @minesweeper.command(name="flag", aliases=["guess"])
    @commands.check(is_game)
    async def ms_flag(self, ctx: Context, cells: commands.Greedy[boardgames.Cell]):
        """Flags a cell on the board.
        cells are referenced by column then row for example `A2`"""

        game = self._games[ctx.channel]

        for cell in cells:
            game.flag(*cell)

        if game.last_state is not None:
            try:
                await game.last_state.delete()
            except Exception:
                pass
        game.last_state = await ctx.send(f">>> {game}")


    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def battleship(self, ctx: commands.Context) -> None:
        """
        Play a game of Battleship with someone else!
        This will set up a message waiting for someone else to react and play along.
        The game takes place entirely in DMs.
        Make sure you have your DMs open so that the bot can message you.
        """
        if self.already_playing(ctx.author):
            await ctx.send("You're already playing a game!")
            return

        if ctx.author in self.waiting:
            await ctx.send("You've already sent out a request for a player 2.")
            return

        announcement = await ctx.send(
            "**Battleship**: A new game is about to start!\n"
            f"Press {HAND_RAISED_EMOJI} to play against {ctx.author.mention}!\n"
            f"(Cancel the game with {CROSS_EMOJI}.)"
        )
        self.waiting.append(ctx.author)
        await announcement.add_reaction(HAND_RAISED_EMOJI)
        await announcement.add_reaction(CROSS_EMOJI)

        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add",
                check=partial(self.predicate, ctx, announcement),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            self.waiting.remove(ctx.author)
            await announcement.delete()
            await ctx.send(f"{ctx.author.mention} Seems like there's no one here to play...")
            return

        if str(reaction.emoji) == CROSS_EMOJI:
            self.waiting.remove(ctx.author)
            await announcement.delete()
            await ctx.send(f"{ctx.author.mention} Game cancelled.")
            return

        await announcement.delete()
        self.waiting.remove(ctx.author)
        if self.already_playing(ctx.author):
            return
        game = GameBattleShip(self.bot, ctx.channel, ctx.author, user)
        self.games.append(game)
        try:
            await game.start_game()
            self.games.remove(game)
        except discord.Forbidden:
            await ctx.send(
                f"{ctx.author.mention} {user.mention} "
                "Game failed. This is likely due to you not having your DMs open. Check and try again."
            )
            self.games.remove(game)
        except Exception:
            # End the game in the event of an unforseen error so the players aren't stuck in a game
            await ctx.send(f"{ctx.author.mention} {user.mention} An error occurred. Game failed.")
            self.games.remove(game)
            raise

    @battleship.command(name="ships", aliases=("boats",))
    async def battleship_ships(self, ctx: commands.Context) -> None:
        """Lists the ships that are found on the battleship grid."""
        embed = discord.Embed(colour=Colours.blue)
        embed.add_field(name="Name", value="\n".join(SHIPS))
        embed.add_field(name="Size", value="\n".join(str(size) for size in SHIPS.values()))
        await ctx.send(embed=embed)


    @commands.command()
    async def rps(self, ctx: Context, move: str) -> None:
        """Play the classic game of Rock Paper Scissors with your own sir-lancebot!"""
        move = move.lower()
        player_mention = ctx.author.mention

        if move not in CHOICES and move not in SHORT_CHOICES:
            raise commands.BadArgument(f"Invalid move. Please make move from options: {', '.join(CHOICES).upper()}.")

        bot_move = choice(CHOICES)
        # value of player_result will be from (-1, 0, 1) as (lost, tied, won).
        player_result = WINNER_DICT[move[0]][bot_move[0]]

        if player_result == 0:
            message_string = f"{player_mention} You and **{self.bot.user.name}** played {bot_move}, it's a tie."
            await ctx.reply(message_string)
        elif player_result == 1:
            await ctx.reply(f"{player_mention} **{self.bot.user.name}** {bot_move}! {ctx.author.name} won!")
        else:
            await ctx.reply(f"{player_mention} **{self.bot.user.name}** {bot_move}! {ctx.author.name} lost!")