function initMap() {
    var austin = {
        lat: 30.2672,
        lng: -97.7341
    };
    var map = new google.maps.Map(document.querySelector('#map'), {
        zoom: 12,
        center: austin
    });

    function addDevice(device) {
        var marker = new google.maps.Marker({
            position: { lat: device.lat, lng: device.lng },
            map: map,
            title: device.appId + ': ' + device.eui,
            draggable: true
        });

        device.marker = marker;

        marker.addListener('click', function() {
            var config = {
                type: 'line',
                data: {
                    labels: device.temperature.map(function(p) { return new Date(p.ts).toLocaleTimeString().split(' ')[0]; }),
                    datasets: [{
                        backgroundColor: window.chartColors.red,
                        borderColor: window.chartColors.red,
                        data: device.temperature.map(function(p) { return p.value; }),
                        fill: false
                    }]
                },
                options: {
                    responsive: true,
                    animation: false,
                    title: {
                        display: true,
                        text: 'Temperature'
                    },
                    tooltips: {
                        mode: 'index',
                        intersect: false,
                    },
                    hover: {
                        mode: 'nearest',
                        intersect: true
                    },
                    scales: {
                        xAxes: [{
                            display: true,
                            scaleLabel: {
                                display: false
                            }
                        }],
                        yAxes: [{
                            display: true,
                            ticks: {
                                suggestedMin: 0,
                                suggestedMax: 50
                            },
                            scaleLabel: {
                                display: true,
                                labelString: 'temperature (pcs/0.01cf)'
                            }
                        }]
                    },
                    legend: {
                        display: false
                    }
                }
            };

            var olId = 'overlay-' + device.eui;

            var infowindow = new google.maps.InfoWindow({
                content: '<div id="' + olId + '"><p class="eui">Device </p><p><canvas width="300" height="200"></canvas></p></div>'
            });

            infowindow.open(map, this);
            infowindow.addListener('domready', () => {
                var o = document.querySelector('#' + olId);
                var ctx = o.querySelector('canvas').getContext('2d');
                var line = new Chart(ctx, config);

                socket.on('temperature-change', function pc(d, ts, value) {
                    if (o !== document.querySelector('#' + olId)) {
                        socket.removeListener('temperature-change', pc);
                        return;
                    }
                    if (d.appId !== device.appId || d.devId !== device.devId) {
                        return;
                    }

                    config.data.labels.push(new Date(ts).toLocaleTimeString().split(' ')[0]);
                    config.data.datasets[0].data.push(value);

                    var len = config.data.labels.length;

                    if (len > 30) {
                        config.data.labels = config.data.labels.slice(len - 30);
                        config.data.datasets[0].data = config.data.datasets[0].data.slice(len - 30);
                    }

                    line.update();
                });

                document.querySelector('#' + olId + ' .eui').textContent = 'Device ' + device.eui + ' (' + device.appId + ')';
            });
        });

        marker.addListener('dragend', function(evt) {
            console.log('new lat/lng is', device.appId, device.devId, evt.latLng.lat(), evt.latLng.lng());

            socket.emit('location-change', device.appId, device.devId, evt.latLng.lat(), evt.latLng.lng());
        });
    }

    window.addDevice = addDevice;

    window.devices.forEach(addDevice);

}
