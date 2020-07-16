import React, { useState, useEffect } from "react";
import { Chart } from "react-charts";

const ENDPOINT = "ws://127.0.0.1:5555/ws";
const socket = new WebSocket(ENDPOINT);

function App() {
  const [socketData, setSocketData] = useState([{ data: [] }]);

  useEffect(() => {
    socket.onmessage = async (data) => {
      let buffer = await data.data.arrayBuffer();
      console.log(buffer);
      setSocketData(new Uint8Array(buffer));
    };
  }, []);

  const data = React.useMemo(
    () => [
      {
        showpoints: false,
        label: "Series 1",
        data: [...socketData].map((datum, idx) => [idx, datum]),
      },
    ],
    [socketData]
  );

  const series = React.useMemo(
    () => ({
      showPoints: false,
    }),
    []
  );

  const axes = React.useMemo(
    () => [
      { primary: true, type: "linear", position: "bottom" },
      { type: "linear", position: "left" },
    ],
    []
  );

  return (
    <div
      style={{
        width: "1000px",
        height: "500px",
      }}
    >
      <Chart data={data} series={series} axes={axes} />
    </div>
  );
}

export default App;
