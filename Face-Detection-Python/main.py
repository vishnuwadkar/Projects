import cv2

faceCap = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

if faceCap.empty():
    print("Error: Unable to load Haar cascade file.")
    exit()

video_cap = cv2.VideoCapture(0)
if not video_cap.isOpened():
    print("Cannot open camera")
    exit()

while True:
    ret, videoData = video_cap.read(1)       #store the captured video in a variable
    if not ret:
        print("Can't receive frame (stream end?). Exiting ...")
        break
    if videoData is None or videoData.size == 0:
        print("No frame captured")
        break
    col = cv2.cvtColor(videoData, cv2.COLOR_BGR2GRAY)     #to convert the captured image into gray color so the face muscles are distinctly visible
    # Detect faces in the frame
    faces = faceCap.detectMultiScale(
        col,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
        flags=cv2.CASCADE_SCALE_IMAGE
    )

    # Draw rectangles around the detected faces
    for (x, y, w, h) in faces:
        cv2.rectangle(videoData, (x, y), (x + w, y + h), (0, 255, 0), 2)

    cv2.imshow("video_live", videoData)     #display the captured video
    if cv2.waitKey(1) & 0xFF == ord("a"):   #to stop capturing on pressing 'a'
        break
video_cap.release()
cv2.destroyAllWindows()