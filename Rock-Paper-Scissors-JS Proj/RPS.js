let userScore = 0;
let compScore = 0;
const msg = document.querySelector(".result")
const choices = document.querySelectorAll(".choices")
let man = document.querySelector("#man")
let comp = document.querySelector("#comp")
let reset = document.querySelector("#reset")
let userb = document.querySelector(".userbox")
let compb = document.querySelector(".compbox")

const genCompChoice = () => {
    let opt = ["rock", "paper", "scissors"];        //an array with three choices
    let rdmChoice = opt[Math.floor(Math.random() * 3)];  //generating random number between 0 to 2
    return rdmChoice;   //returns any one option from the array
}

const winTrack = () => {        //for coloring the border according to high scorer
    if (userScore > compScore) {
        userb.style.border = "8px solid #11ff00"
        compb.style.border = "8px solid red"
    } else if (userScore < compScore) {
        compb.style.border = "8px solid #11ff00"
        userb.style.border = "8px solid red"
    }
}

const gameDraw = (choiceId) => {    //gameDraw function
    msg.innerText = `Game Draw! Computer chose ${choiceId}`
    msg.style.backgroundColor = "yellow"
}
const showWinner = (userWin, compChoice) => {   //winner fucntion that takes boolean value and computer's choice as arg
    if (userWin) {  //if true
        msg.innerText = `You Win! Computer chose ${compChoice}`
        msg.style.backgroundColor = "#11ff00"
        userScore++;    //increase user score
        man.innerText = userScore   //display on the score board
    } else {    //if flase ie not win
        msg.innerText = `You Lost! Computer chose ${compChoice}`
        msg.style.backgroundColor = "red"
        compScore++;    //increase comp score
        comp.innerText = compScore; //display on the score board
    }
}

const playGame = (choiceId) => {    //play game func that takes our choice as an arg
    let compChoice = genCompChoice()    //taking comp's choice

    if (choiceId == compChoice) {   //if choices equal then draw
        gameDraw(choiceId)
    } else {
        let userWin = true; //initializing user win
        if (choiceId === "rock") {
            //scissors or paper
            userWin = compChoice === "paper" ? false : true   //user chooses rock and comp choses paper, then make user choice false
        } else if (choiceId === "paper") {
            //rock or scissors
            userWin = compChoice === "scissors" ? false : true  //user chooses paper and comp chooses scissors, then make user win false
        }
        else {   //user has scissors
            //rock or paper
            userWin = compChoice === "rock" ? false : true  //user chooses scissors and comp chooses rock, make user win false
        }
        showWinner(userWin, compChoice) //boolean provided as arg to showWinner
        winTrack()  //win Track func called
    }
}

choices.forEach((choice) => {   //for all choices
    choice.addEventListener("click", () => {    //on clicking the choice
        let choiceId = choice.getAttribute("id")
        playGame(choiceId)  //choice provided as arg to playgame()
    })
})

reset.addEventListener("click", () => { //resetting
    userScore = 0;
    man.innerText = userScore
    compScore = 0;
    comp.innerText = compScore;
    msg.innerText = "Choose your move!"
    msg.style.backgroundColor = "white"
    compb.style.border = "none"
    userb.style.border = "none"
})
