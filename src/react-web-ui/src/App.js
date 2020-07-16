import React, { useState, useEffect } from "react";
import io from "socket.io-client";
const customParser = require("socket.io-msgpack-parser");

const ENDPOINT = "ws://127.0.0.1:5555/ws";
const socket = new WebSocket(ENDPOINT);

async function onMessageArrived(binary_blob_data) {
  let buffer = await binary_blob_data.arrayBuffer();
  let length = buffer.byteLength;

  let uint = new Uint8Array(buffer);
  for (let i = 0; i < 16; i++) {
    console.log(`uint - index: ${i}, value: ${uint[i]}`);
  }
  let dataView = new DataView(uint.buffer);
  length = 16;
  for (let i = 0; i < length / 4; i++) {
    let value = dataView.getFloat32(i * 4, false);
    console.log(`dataview - index: ${i}, value: ${value}`);
  }
}
function App() {
  const [socketData, setSocketData] = useState("");

  useEffect(() => {
    socket.onmessage = async (data) => {
      let buffer = await data.data.arrayBuffer();
      console.log(buffer);
      setSocketData(new Uint8Array(buffer));
    };
  }, []);

  return <p>Data WOOO {socketData}</p>;
}

export default App;
