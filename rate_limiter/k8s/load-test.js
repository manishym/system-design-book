import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    vus: 1000,               // virtual users
    duration: '60s',         // test duration
};

export default function () {
    const userId = Math.floor(Math.random() * 1000000);
    const res = http.get(`http://<your-loadbalancer-ip>/api?user=${userId}`);
    check(res, { 'status is 200': (r) => r.status === 200 });
    sleep(0.01); // slight delay to mimic real users
}
