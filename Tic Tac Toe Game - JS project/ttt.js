let boxes = document.querySelectorAll(".box")
let reset = document.querySelector(".reset")
let msgcont = document.querySelector(".msgcont")
let msg = document.querySelector("#msg")
let msgbtn = document.querySelector(".msgbtn")
let count = 1;  //counter variable for game draw
let turn0 = true; //turn tracking

const winPattern = [        //recording a 2d array of all the winning patterns 
    [0,1,2],
    [0,3,6],
    [0,4,8],
    [1,4,7],
    [2,5,8],
    [2,4,6],
    [3,4,5],
    [6,7,8]
];
const enableBox=()=>{   //enables all the boxes again for reset
    for(box of boxes){
        box.disabled = false;
        box.innerText=""
    }
}
const resetGame =()=>{  //reset game function
    turn0=true;
    enableBox();
    msgcont.classList.add("hide")   //remove the hide class
    count=1     //resetting the counter variable
}
const winner=(winplr)=>{    //win function
    msg.innerHTML = `Congratulations! Winner is ${winplr}`
    msgcont.classList.remove("hide")    //displaying the winner interface
}
const disablebox =()=>{     //disables the boxes either after winning or game draw
    for(box of boxes){
        box.disabled = true;
    }
}

const checkWin = ()=>{  //check win condition for checking patterns on every click
    if(count==9){   //if all boxes filled
        msg.innerText="GAME DRAW!"  //displays game draw
        disablebox()
        msgcont.classList.remove("hide")    //display game draw interface
    }
    else{       //else check for the win condition

        for(let pattern of winPattern){     //for every array in winPattern 2d array
            let pos1 = boxes[pattern[0]].innerText; 
            let pos2 = boxes[pattern[1]].innerText;
            let pos3 = boxes[pattern[2]].innerText;
            
            if(pos1 != "" && pos2 != "" && pos3 != ""){ //if all the three boxes are filled
                if(pos1 === pos2 && pos2 ===  pos3){  //if the recorded pattern positions are of same value
                    disablebox();   //disable rest of the boxes
                    setTimeout(winner,700,pos1)    //declare winner after 1sec delay and pass the winner value as arg to winner function
                }
            }
        }
        count++ //increase the counter for every click 
    }
}

boxes.forEach((box)=>{  //for all boxes 
    box.addEventListener("click", ()=>{     //on clicking...
        if(turn0){  //on 'o's turn
            box.innerText = "O" //mark 'o' in the box
            box.style.color = "red"
            turn0 = false;  //change the turn variable
        }
        else{
            box.innerText = "X"
            box.style.color = "green"
            turn0 = true;
        }
        box.disabled = true;    //so the value isn't changes again
        checkWin();     //check for win condition on every click
    })

})

reset.addEventListener("click",resetGame)   //reset on 'reset' button
msgbtn.addEventListener("click",resetGame)  //reset on 'new game' button
