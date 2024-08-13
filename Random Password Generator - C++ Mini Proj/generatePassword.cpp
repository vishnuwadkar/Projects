#include<iostream>
#include<cstdlib>   //to use random function
#include<string>    //to claculate string size
#include<ctime>     //to get current time data
using namespace std;

string getPassword(int length){
    string password = " ";   //initializing password with NULL
    string characters ="aquickbrownfoxjumpsoverthelazydogAQUICKBROWNFOXJUMPSOVERTHELAZYDOG1234567890@.#$*";
    //storing all possible characters trick
    int charSize = characters.size();   //calculating size of above string
   //srand(time(0)); //generating random number using time function
    int randomindex;
    for(int i=0; i<length; i++){
        randomindex = rand() % charSize; //generating random index
        password += characters[randomindex]; //adding character at that index to password
    }
    return password;
}

int main(){
    int length;
    cout<<"Enter the length of the password: ";
    cin>>length;
    string password = getPassword(length);  //function call
    cout<<"Generated password: "<<password;

    return 0;
}