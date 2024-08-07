let boxes = document.querySelectorAll(".box")
let reset = document.querySelector(".reset")
let msgcont = document.querySelector(".msgcont")
let msg = document.querySelector("#msg")
let msgbtn = document.querySelector(".msgbtn")

let turn0 = true; //turn tracking

const winPattern = [
    [0,1,2],
    [0,3,6],
    [0,4,8],
    [1,4,7],
    [2,5,8],
    [2,4,6],
    [3,4,5],
    [6,7,8]
];
const enableBox=()=>{
    for(box of boxes){
        box.disabled = false;
        box.innerText=""
    }
}
const resetGame =()=>{
    turn0=true;
    enableBox();
    msgcont.classList.add("hide")
}
const winner=(winplr)=>{
    msg.innerHTML = `Congratulations! Winner is ${winplr}`
    msgcont.classList.remove("hide")
}
const disablebox =()=>{
    for(box of boxes){
        box.disabled = true;
    }
}

const checkWin = ()=>{
    for(let pattern of winPattern){
        let pos1 = boxes[pattern[0]].innerText;
        let pos2 = boxes[pattern[1]].innerText;
        let pos3 = boxes[pattern[2]].innerText;

        if(pos1 != "" && pos2 != "" && pos3 != ""){
            if(pos1 === pos2 && pos2 ===  pos3){
                console.log("winner!")
                disablebox();
                winner(pos1)
            }
        }
    }
}

boxes.forEach((box)=>{
    box.addEventListener("click", ()=>{
        console.log("Box was clicked");
        if(turn0){
            box.innerText = "O"
            turn0 = false;
        }
        else{
            box.innerText = "X"
            turn0 = true;
        }
        box.disabled = true;
        checkWin();
    })

})

reset.addEventListener("click",resetGame)
msgbtn.addEventListener("click",resetGame)

